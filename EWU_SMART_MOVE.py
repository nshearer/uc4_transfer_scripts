#!/usr/bin/python
'''Utility script to identify and move or copy job output files'''
import os
import sys
import gflags
import subprocess
from fnmatch import fnmatch
from textwrap import dedent
import re
from time import time
import shutil

# File Search Parms

gflags.DEFINE_string(
    'search',
    short_name = 's',
    default    = None,
    help       = "Directory to search file file in.  Uses $HOME by default"
    )

gflags.DEFINE_enum(
    'recurse',
    short_name  = 'r',
    default     = 'no',
    help        = "Search sub directories of search path",
    enum_values = ['yes', 'no']
    )

gflags.DEFINE_string(
    'filename',
    short_name = 'F',
    default    = None,
    help       = "Name of file to act on.  Accepts standard glob (* & ?) patterns",
    )


# File matching parameters

gflags.DEFINE_enum(
    'match_case',
    short_name  = 'C',
    default     = 'yes',
    help        = "Make filename match case sensitive",
    enum_values = ['yes', 'no']
    )

gflags.DEFINE_integer(
    'min_size',
    default      = None,
    help         = "Minimum size of the file in bytes",
    lower_bound  = 0,
    upper_bound  = None
    )

gflags.DEFINE_integer(
    'max_size',
    default      = None,
    help         = "Maximum size of the file in bytes",
    lower_bound  = 0,
    upper_bound  = None
    )

gflags.DEFINE_string(
    'parm_file',
    short_name = 'p',
    default    = None,
    help       = dedent("""\
        Path to parameters file.

        If used, the file must be formatted with simple key=value pairs.

        Such as:
            year = 2015
            month = 02
            day = 23

        Then parms can be used in parameters (search, filename, search_in_file, output_dir, output_filename):
            --output_dir=/u03/upload/home/finance/(pay_year)/(pay_month)_report.txt
        """)
    )

gflags.DEFINE_string(
    'search_in_file',
    short_name = 'I',
    default    = None,
    help       = "Search for text in file"
    )

gflags.DEFINE_string(
    'search_re_in_file',
    short_name = 'R',
    default    = None,
    help       = "Search for text using regular expression in file"
    )

gflags.DEFINE_integer(
    'max_age',
    default      = None,
    help         = "Maximum number of minutes since this file was written to",
    lower_bound  = 0,
    upper_bound  = None
    )



# Output Parms

gflags.DEFINE_enum(
    'verbose',
    short_name  = 'v',
    default     = 'no',
    help        = "Explain why files are being rejected or matched",
    enum_values = ['yes', 'no']
    )


# Processing parms

gflags.DEFINE_string(
    'output_dir',
    short_name = 'o',
    default    = None,
    help       = "Directory to move or copy file to"
    )
gflags.MarkFlagAsRequired('output_dir')

gflags.DEFINE_string(
    'output_filename',
    short_name = 'n',
    default    = None,
    help       = "Name to give file in output directory.  Requires --single_file"
    )

gflags.DEFINE_enum(
    'single_file',
    default     = 'no',
    help        = "Will generate an error if more than one file is matched",
    enum_values = ['yes', 'no']
    )

gflags.DEFINE_enum(
    'overwrite',
    default     = 'no',
    help        = "Will generate an error if trying to overwrite an existing file",
    enum_values = ['yes', 'no']
    )

gflags.DEFINE_enum(
    'must_match',
    default     = 'no',
    help        = "Will generate an error if no files are matched",
    enum_values = ['yes', 'no']
    )

gflags.DEFINE_enum(
    'action',
    short_name  = 'a',
    default     = None,
    help        = "What action to take on matched files",
    enum_values = ['move', 'copy', 'test']
    )

gflags.DEFINE_enum(
    'unix2dos',
    short_name  = 'u',
    default     = 'no',
    help        = "Call unix2dos to change line endings to DOS/Windows format",
    enum_values = ['yes', 'no']
    )



def debug(msg):
    if gflags.FLAGS.verbose == 'yes':
        print msg

ARG_PARMS=dict()


def load_parms():
    flags = gflags.FLAGS
    global ARG_PARMS

    if flags.parm_file is not None:
        if not os.path.exists(flags.parm_file):
            print "ERROR: Pattern file doesn't exist: " + flags.parm_file
            sys.exit(2)
        if not os.path.isfile(flags.parm_file):
            print "ERROR: Pattern file isn't a file: " + flags.parm_file
            sys.exit(2)

        try:
            fh = open(flags.parm_file, 'rt')
            for line in fh.readlines():
                parts = line.strip().split("=")
                if len(parts) > 0 and len(parts[0]) > 0:
                    name = parts[0].strip()
                    value = ("=".join(parts[1:])).strip()
                    debug("Read parameter %s = %s" % (name, value))
                    ARG_PARMS[name] = value
            fh.close()
        except Exception, e:
            print "ERROR: While reading parm file %s:" % (flags.parm_file)
            print "       " + str(e)
            sys.exit(2)


def apply_parms(subject):
    global ARG_PARMS
    for name, value in ARG_PARMS.items():
        name = '(' + name + ')'
        subject = subject.replace(name, value)
    return subject


def list_files_to_consider(search_path):
    '''List files at search path to consider'''
    flags = gflags.FLAGS

    search_path = apply_parms(search_path)

    # Return all files
    if flags.recurse == 'yes':
        debug("Searching %s (recursivly)" % (search_path))
        for dirpath, dirnames, filenames in os.walk(search_path):
            for filename in filenames:
                yield os.path.join(dirpath, filename)
    else:
        debug("Searching %s" % (search_path))
        for filename in os.listdir(search_path):
            path = os.path.join(search_path, filename)
            if os.path.isfile(path):
                yield path


def check_match(path):
    '''Check to see if a file matches the provided parameters'''
    flags = gflags.FLAGS

    filename = os.path.basename(path)
    check_filename = apply_parms(filename)
    if flags.match_case == 'no':
        check_filename = check_filename.lower()

    # Check filename
    if flags.filename is not None:
        match_filename = apply_parms(flags.filename)
        if flags.match_case == 'no':
            match_filename = match_filename.lower()
        if not fnmatch(check_filename, match_filename):
            debug(path + ": no match: Does not match filename pattern " + match_filename)
            return False

    # Check minimum size
    if flags.min_size is not None:
        if os.path.getsize(path) < flags.min_size:
            debug(path + ": no match: File too small")
            return False

    # Check maximum size
    if flags.max_size is not None:
        if os.path.getsize(path) > flags.max_size:
            debug(path + ": no match: File too big")
            return False

    # Check file age
    if flags.max_age is not None:
        stat = os.stat(path)
        file_modified = max(int(stat.st_mtime), int(stat.st_ctime))
        age = (time() - file_modified) / 60
        if age > flags.max_age:
            debug(path + ": no match: Modified %.02f minutes ago (> %d) " % (age, flags.max_age))
            return False

    # Check file contents (static search)
    if flags.search_in_file is not None:
        found = False
        search_in_file = apply_parms(flags.search_in_file)

        try:
            fh = open(path, 'rt')
            for line in fh.readlines():
                if search_in_file in line:
                    found = True
                    break
            fh.close()
        except Exception, e:
            print "ERROR while searching contents of %s:" % (path)
            print "      " + str(e)
            sys.exit(2)

        if not found:
            debug(path + ": no match: Does not have search string: " + search_in_file)
            return False

    # Check file contents (regular expression)
    if flags.search_re_in_file is not None:
        found = False
        search_re_pat = re.compile(flags.search_re_in_file)

        try:
            fh = open(path, 'rt')
            for line in fh.readlines():
                if search_re_pat.search(line):
                    found = True
                    break
            fh.close()
        except Exception, e:
            print "ERROR while searching contents of %s:" % (path)
            print "      " + str(e)
            sys.exit(2)

        if not found:
            debug(path + ": no match: Does not match expression: " + flags.search_re_in_file)
            return False

    # Else, matches
    debug(path + ": MATCHES")
    return True


def act_on_file(path):
    flags = gflags.FLAGS

    dst_filename = os.path.basename(path)
    if flags.output_filename is not None:
        dst_filename = apply_parms(flags.output_filename)

    dst_path = os.path.join(flags.output_dir, dst_filename)

    if flags.overwrite == 'no':
        if os.path.exists(dst_path):
            print "ERROR: Destination file %s already exists" % (dst_path)
            sys.exit(2)

    if flags.action == 'test':
        print "(test) %s -> %s" % (path, dst_path),

    elif flags.action == 'copy':
        print "cp %s -> %s" % (path, dst_path), 
        shutil.copy(path, dst_path)

    elif flags.action == 'move':
        print "mv %s -> %s" % (path, dst_path), 
        os.rename(path, dst_path)

    else:
        print "ERROR: Unhandled action: " + flags.action
        sys.exit(2)

    # Handle unix2dos
    if flags.unix2dos == 'yes':
        print " (+unix2dos)"
        rtncode = subprocess.call(
            ['/usr/bin/unix2dos', dst_path],
            stdin=None,
            stdout=None,
            stderr=None)
        if rtncode != 0:
            print "ERROR: unix2dos return code %s" % (rtncode)
    else:
        print ""


if __name__ == '__main__':

    print "TRACE:", " ".join(sys.argv)
    print ""

    # Parse command line arguments
    try:
        argv = gflags.FLAGS(sys.argv)
    except gflags.FlagsError, e:
        print 'USAGE ERROR: %s\nUsage: %s ARGS\n%s' % (e, sys.argv[0], gflags.FLAGS)
        sys.exit(1)
    flags = gflags.FLAGS

    load_parms()

    # Determine search path
    search_path = flags.search
    if search_path is None:
        if os.environ.has_key('HOME'):
            search_path = os.environ['HOME']
    if search_path is None:
        print "ERROR: No search path specified, and can't find home"
        sys.exit(1)
    if not os.path.exists(search_path):
        print "ERROR: Search path does not exist: " + search_path
        sys.exit(1)
    if not os.path.isdir(search_path):
        print "ERROR: Search path is not a directory: " + search_path
        sys.exit(1)

    # Find files to act on
    matched = list()
    for candidate in list_files_to_consider(search_path):
        if check_match(candidate):
            matched.append(candidate)

    # Check matches
    if flags.single_file == 'yes' and len(matched) > 1:
        print "ERROR: Multiple files matched:"
        for path in matched:
            print " - " + path
        sys.exit(2)

    if flags.must_match == 'yes' and len(matched) < 1:
        print "ERROR: No files found"
        sys.exit(2)

    # Act on files
    for path in matched:
        act_on_file(path)

    print ""
    print "Acted on %d file(s)" % (len(matched))

