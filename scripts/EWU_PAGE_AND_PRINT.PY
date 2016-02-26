#!/usr/bin/python
'''Script for printing files on Linux

Summary
-------

Specifically tailored for Payroll and Benefit printers.

These scripts use a configuration file to define the number of lines
and columns that can be printed on each page in order to work around
some of the inadiquate print drivers in CentOS.


Config file format
------------------

    ; Printer details for printing Payroll Vendor reports

    [defaults]

    font = Courier

    landscape_8_line_width = 152
    landscape_8_lines_per_page = 59
    landscape_8_enscript_indent = 0

    landscape_9_line_width = 135
    landscape_9_lines_per_page = 53
    landscape_9_enscript_indent = 0

    landscape_10_line_width = 122
    landscape_10_lines_per_page = 48
    landscape_10_enscript_indent = 0

    portrait_8_line_width = 109
    portrait_8_lines_per_page = 82
    portrait_8_enscript_indent = 0

    portrait_9_line_width = 97
    portrait_9_lines_per_page = 74
    portrait_9_enscript_indent = 0

    portrait_10_line_width = 87
    portrait_10_lines_per_page = 67
    portrait_10_enscript_indent = 0


    [payroll]
    device = DEVICE-NAME
'''
VERSION='1.2.0'

import os
import sys
import ConfigParser
import gflags
import subprocess
from datetime import datetime
from tempfile import TemporaryFile

def abort(msg):
    print "ERROR:", msg
    print "ABORTING"
    sys.exit(2)


# -- Command Line Options -----------------------------------------------------

gflags.DEFINE_string(
    'path',
    short_name = 'i',
    default    = None,
    help       = "File to print"
    )
gflags.MarkFlagAsRequired('path')

gflags.DEFINE_string(
    'printer',
    short_name  = 'p',
    default     = None,
    help        = "Which printer alias to print to",
    )
gflags.MarkFlagAsRequired('printer')
    
gflags.DEFINE_string(
    'config',
    short_name  = 'c',
    default     = None,
    help        = "Path to printer config file",
    )
gflags.MarkFlagAsRequired('config')
    
gflags.DEFINE_string(
    'font',
    short_name  = 'u',
    default     = 'Courier',
    help        = "Name of the font to use",
    )

ORIENTATIONS = ['portrait', 'landscape']

gflags.DEFINE_enum(
    'orientation',
    short_name  = 'o',
    default     = 'landscape',
    help        = "How to orient the output page",
    enum_values = ORIENTATIONS,
    )
gflags.MarkFlagAsRequired('orientation')

STANDARD_FONT_SIZES = [8, 9, 10]

gflags.DEFINE_enum(
    'fontsize',
    short_name  = 'f',
    default     = None,
    help        = "Size (in points) of the font",
    enum_values = [str(i) for i in STANDARD_FONT_SIZES]
    )

YES_NO_OPTS = ('Y', 'N')

gflags.DEFINE_enum(
    'footer',
    default     = 'Y',
    help        = "Create footer at the bottom of the page",
    enum_values = YES_NO_OPTS,
    )

gflags.DEFINE_enum(
    'filename',
    short_name = 'F',
    default    = 'N',
    help       = "Include filename in footer",
    enum_values = YES_NO_OPTS,
    )

gflags.DEFINE_enum(
    'page_num',
    short_name = 'P',
    default    = 'N',
    help       = "Include page x of y in the footer",
    enum_values = YES_NO_OPTS,
    )

gflags.DEFINE_string(
    'title',
    short_name = 'T',
    default    = None,
    help       = "Include title to print in footer (probably instead of filename)"
    )

gflags.DEFINE_enum(
    'ctime',
    short_name = 'C',
    default    = 'N',
    help       = "Include file creation time in the footer",
    enum_values = YES_NO_OPTS,
    )

# gflags.DEFINE_integer(
#     'header_lines',
#     short_name   = 'H',
#     default      = 0,
#     help         = "Number of lines in the header on the first page of files to be printed",
#     lower_bound  = None,
#     upper_bound  = None
#     )


# -- Printer Objects ----------------------------------------------------------

class PrinterConfigFile(object):
    '''Parser for reading printer config file'''

    def __init__(self):
        self.path = gflags.FLAGS.config
        self._config = None

        self._load_config()


    def _load_config(self):
        if not os.path.exists(self.path):
            abort("Config path %s doesn't exist" % (self.path))
        try:
            fh = open(self.path, 'rt')
            self._config = ConfigParser.RawConfigParser()
            self._config.readfp(fh)
            fh.close()
        except Exception, e:
            abort("Failed to parse config file %s: %s" % (self.path, str(e)))


    def list_printers(self):
        '''List the defined printer names from the config'''
        for section in self._config.sections():
            if section.lower() != 'defaults':
                yield PrinterConfig(self, section)


    def get_printer(self, name):
        if not self._config.has_section(name):
            abort("Printer %s not defined in %s" % (name, self.path))
        return PrinterConfig(self, name)


    DEFAULTS={
        'landscape_8_line_width':       152,
        'landscape_8_lines_per_page':   59,
        'landscape_8_enscript_indent':  0,

        'landscape_9_line_width':       135,
        'landscape_9_lines_per_page':   53,
        'landscape_9_enscript_indent':  0,

        'landscape_10_line_width':      122,
        'landscape_10_lines_per_page':  48,
        'landscape_10_enscript_indent': 0,

        'portrait_8_line_width':        109,
        'portrait_8_lines_per_page':    82,
        'portrait_8_enscript_indent':   0,

        'portrait_9_line_width':        97,
        'portrait_9_lines_per_page':    74,
        'portrait_9_enscript_indent':   0,

        'portrait_10_line_width':       87,
        'portrait_10_lines_per_page':   67,
        'portrait_10_enscript_indent':  0,    
    }

    def get_option_value(self, printer_name, opt_key):
        if self._config.has_option(printer_name, opt_key):
            return self._config.get(printer_name, opt_key)

        # Check for default value in ini
        if self._config.has_option('defaults', opt_key):
            return self._config.get('defaults', opt_key)

        # Use built in defaults as a fallback
        if self.DEFAULTS.has_key(opt_key):
            return self.DEFAULTS[opt_key]

        return None


class PrinterConfig(object):
    '''Wrapper for the requested printer'''

    def __init__(self, config_file, printer_name):
        self._config_file = config_file
        self.name = printer_name

    def get_page_config(self, orientation, fontname, fontsize):
        return PrinterPageConfig(self._config_file, self, orientation, fontname, fontsize)

    def list_page_configs(self, orientation, fontname):
        for fontsize in STANDARD_FONT_SIZES:
            yield PrinterPageConfig(self._config_file, self, orientation, fontname, fontsize)

    @property
    def device(self):
        return self._config_file.get_option_value(self.name, 'device')
    


class PrinterPageConfig(object):
    '''Wrapper for details on a specific font size on a printer'''

    def __init__(self, config_file, printer_config, orientation, fontname, fontsize):
        self._config_file = config_file
        self.printer = printer_config
        self.orientation = orientation
        self.fontname = fontname
        self.fontsize = fontsize


    def _get_value(self, option):
        '''Get the configured value for this key.'''
        # Build config entry key
        key = '_'.join([self.orientation, str(self.fontsize), option])

        # Check for printer specific value
        value = self._config_file.get_option_value(self.printer.name, key)

        # Error
        if value is None:
            abort("Config %s has no value for option %s for printer %s" % (
                self._config_file.path, option, self.printer.name))

        return value


    @property
    def max_line_width(self):
        return int(self._get_value('line_width'))

    @property
    def lines_per_page(self):
        return int(self._get_value('lines_per_page'))

    @property
    def enscript_indent(self):
        return int(self._get_value('enscript_indent'))


gflags.DEFINE_bool(
    'verbose',
    short_name = 'v',
    default    = False,
    help       = "Printer extra detail about print job"
    )

def debug(msg):
    if gflags.FLAGS.verbose:
        print msg
def debug_var(varname, value):
    debug("%-15s %s" % (varname + ':', str(value)))


gflags.DEFINE_bool(
    'dryrun',
    short_name = 'n',
    default    = False,
    help       = "Don't print.  Useful with -v to debug"
    )

def is_yes_no(value):
    if value.upper() == 'Y':
        return True
    return False


# -- Main ---------------------------------------------------------------------

if __name__ == '__main__':

    # Parse command line arguments
    try:
        argv = gflags.FLAGS(sys.argv)

        if not os.path.exists(gflags.FLAGS.path):
            raise gflags.FlagsError("Input file does not exist: " + gflags.FLAGS.path)
    except gflags.FlagsError, e:
        print 'USAGE ERROR: %s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], gflags.FLAGS)
        sys.exit(1)
    flags = gflags.FLAGS

    # Re-apply default parameter values.  UC4 passes "--font=" if no parm value supplied
    flags.font = flags.font or 'Courier'
    flags.orientation = flags.orientation or 'landscape'
    flags.footer = flags.footer or 'Y'
    flags.filename = flags.filename or 'N'
    flags.page_num = flags.page_num or 'N'
    flags.ctime = flags.ctime or 'N'

    # Calc font name
    font_name = flags.font

    # Calc page orientation
    orientation = flags.orientation
    debug_var("orientation", orientation)

    # Load printer config
    config = PrinterConfigFile()
    print str([p.name for p in config.list_printers()])

    printer = config.get_printer(flags.printer)

    # Load all content from file to print into mem for easy logic
    max_line_width = 0
    file_ctime = None
    try:
        fh = open(flags.path, 'rt')
        src = list()
        for line in fh.readlines():
            line = line.rstrip()
            src.append(line)
            max_line_width = max(max_line_width, len(line))
        fh.close()
        debug_var('src max width', max_line_width)
        files_stat = os.stat(flags.path)
        file_ctime = datetime.fromtimestamp(files_stat.st_ctime)
        debug_var('ctime', file_ctime)
    except Exception, e:
        abort("ERROR Reading from %s: %s" % (flags.path, str(e)))
 
    # Calc font size
    fontsize = flags.fontsize
    if fontsize is None:
        for page_spec in reversed(sorted(printer.list_page_configs(orientation, font_name), key=lambda p: p.fontsize)):
            if page_spec.max_line_width >= max_line_width:
                fontsize = i
                break
    debug_var('font size', fontsize)
    if fontsize is None:
        fontsize = min(STANDARD_FONT_SIZES)

    page_spec = printer.get_page_config(orientation, font_name, fontsize)

    # Calc Footer format 
    has_footer = is_yes_no(flags.footer)
    footer_fmt = None
    if has_footer:
        footer_fmt = list()
        if is_yes_no(flags.ctime):
            footer_fmt.append('{ctime}')
        if flags.title is not None:
            footer_fmt.append('{title}')
        if is_yes_no(flags.filename):
            footer_fmt.append('{filename}')
        if is_yes_no(flags.page_num):
            footer_fmt.append('Page {page_num} of {page_count}')
        footer_fmt = ' - '.join(footer_fmt)
    debug_var('has footer', has_footer)
    debug_var('footer format', footer_fmt)

    # Page output
    lines_per_page = page_spec.lines_per_page
    if has_footer:
        lines_per_page -= 1
    debug_var('lines per page', lines_per_page)

    pages = list()
    page = list()
    pages.append(page)

    for line in src:
        # Need to finish page?
        if len(page) >= lines_per_page:
            page = list()
            pages.append(page)
        page.append(line)


    if has_footer:
        for i, page in enumerate(pages):

            # Pad pages to max lines to make sure footers are at the bottom of pages
            while len(page) < lines_per_page:
                page.append("")
                    
            # Add footers
            footer = footer_fmt

            footer = footer.replace('{title}', str(flags.title))
            footer = footer.replace('{ctime}', file_ctime.strftime('%a, %b %d %I:%M%p'))
            footer = footer.replace('{filename}', os.path.basename(flags.path))
            footer = footer.replace('{page_num}', str(i+1))
            footer = footer.replace('{page_count}', str(len(pages)))

            footer = ' '*(page_spec.max_line_width - len(footer)) + footer

            page.append(footer)

    # Collapse pages
    for i, page in enumerate(pages):
        pages[i] = "\n".join(page)
    pages = chr(12).join(pages)     # chr 12 is Form Feed (^L)

    # Calc enscript parms
    cmd = [
        '/usr/bin/enscript',
        '-P', printer.device,
        '-f', '%s%d' % (font_name, int(fontsize)),
        '-B'
    ]
    if orientation == 'landscape':
        cmd.append('-r')
    if page_spec.enscript_indent is not None and page_spec.enscript_indent != 0:
        cmd.append('-i')
        cmd.append(str(page_spec.enscript_indent))
    debug_var('enscript', str(cmd))

    # Print
    print ""
    print "%s version %s" % (os.path.basename(sys.argv[0]), VERSION)
    if not flags.dryrun:
        # Create temp file to print from
        fh = TemporaryFile(mode='w+t')
        fh.write(pages)
        fh.seek(0)

        # Print temp file
        print "printing %s to %s" % (flags.path, printer.device)
        print "$> " + " ".join(cmd)
        rtncode = subprocess.call(cmd,
            stdin=fh,
            stdout=sys.stdout,
            stderr=sys.stdout)
        if rtncode != 0:
            print "ERROR: enscrypt returned code %s" % (rtncode)
            sys.exit(rtncode)

        # Clean up
        fh.close()
        print ""
        print "Finished"
    else:
        print "Not printing %s for %s (dry run)" % (flags.path, printer.device)
