#!/usr/bin/python
'''
EWU_SMB.PY - Generic Shell to Perform Transfers to/from Windows file Shares
Written by Nathan Shearer


Summary
-------

This script wraps a call to /usr/bin/smbclient to push and pull a files from/to
this server from/to a remote Window file share.  It is inteded to be called by
an AppWorx module named EWU_SMB.


Modes
-----

This script is intended to solve multiple use cases.  Use the MODE parameter
to specify the use case.

    GET_1   - Get 1 file from a remote Windows server to local host
    GET_M   - Get multiple files from a remote Windows server to this local host
    PUT_1   - Put 1 files from this local host to a remote Windows server
    PUT_M   - Put multiple files from this local host to a remote Windows server


Parameters
----------

Here are the names and general explanations of the script parameters.  Many
parameters have different uses depending on the mode value.  Specific meanings
for each mode are listed below this section.

 [ 1] RHOST: The remote host (either resolvable name or IP address)
 [ 2] RUSER: Username to use for connecting to remote host
 [ 3] MODE:  Mode of operation (GET_1, GET_M, PUT_1, PUT_M)
 [ 4] LPATH: Path to local folder or file
 [ 5] RPATH: Path to remote folder or file (relative to share folder)
 [ 6] CREDS: Path to the credentials file.  See below for syntax.
 [ 7] DEL:   Delete on success? (DEL or NO_DEL)
 [ 8] LIMIT: Limit number of files retrieved, or ALL
 [ 9] OVERW: Overwrite existing files? (OVERWRITE or ERROR_EXISTING)
 [10] MULTI: Action if multiple files match (MULTI_OK, MULTI_ERROR, or MULTI_PICK_1)
 [11] REQ:   What to do if no files are found (REQUIRED or OPTIONAL)
 [12] CONV:  Convert file format to/from DOS (CONV or NO_CONV)

The Windows share path:
    //server/share/folder_a/folder_b/file.dat
Would be represented as:
    RHOST: server
    RPATH: share/folder_a/folder_b/file.dat

Note on wildcards:
    Sometimes paramters accept wildcards (path globbing) where * matches any
    sequence of characters and ? matches any single character.

    WARNING:
      - You should always quote field values with wildcards with single quotes
        to prevent wildcard expansion by UC4 when this script is being called.
      - Wildcards can only be used for filenames, not directories

For GET_1 mode:
    LPATH: Is the path to save the file to on the local host including filename.
    RPATH: Is the path to the file on the remote host to copy the file from
           including the filename.  Wildcards may be used if the remote filename
           is not known.
    MULTI: If the filename pattern in RPATH matches multiple files and
           MULTI=MULTI_ERROR, then the script will error without copying any
           files.  Otherwise, one file will be chosen randomly to be copied.
           MULTI_OK value not allowed in this mode.
    DEL:   If DEL, then the file copied on the remote server will be
           deleted if the transfer succeeds.
    LIMIT: Must be ALL for this mode
    REQ:   Must be REQUIRED for this mode
    CONV:  Run dos2unix

For GET_M mode:
    LPATH: Is the path to the directory on the local host to save any copied
           files.
    RPATH: Is the path to the files to be copied including filenames with optional
           wildcards to match multiple files.
    MULTI: Must be MULTI_OK for this mode
    DEL:   If DEL, then each file copied from the remote server will be deleted
           after successfully transfered.  It's possible for some files to be
           transfered and deleted, but not all, if an error occurs.
    LIMIT: If ALL, then copy all files found.  Else, only the number of files
           specified here will be transfered (chosen randmonly) and the others
           will be ignored.
    REQ:   If REQUIRED and no files are found to transfer, then an error will
           be returned
    CONV:  Run dos2unix

For PUT_1 mode:
    LPATH: Is the path to the file on the local host to push up including
           the filename.  Wildcards may be used if local filename is not known.
    RPATH: Is the full path to the file on the remote host to place the file
           including the filename.
    MULTI: If the filename pattern in LPATH matches multple files, and this
           value is MULTI_ERROR, then an error code will be returned.  If
           value is MULTI_PCIK_1, then one of the matching files will be chosen
           at random to send.
           Value MULTI_OK is not allowed for this mode.
    DEL:   If DEL, then each file successfully copied will be deleted from the
           local host.
    LIMIT: Must be ALL for this mode
    REQ:   Must be REQUIRED for this mode
    CONV:  Run unix2dos

For PUT_M mode:
    LPATH: Is the path to the files on the local host to push up including a
           filename pattern with wildcards.
    RPATH: Is the path to the directory on the remote server to copy files
           to.
    MULTI: Must be MULTI_OK for this mode
    DEL:   If DEL, then each file successfully copied will be deleted from the
           local host.
    LIMIT: If ALL, then copy all files found.  Else, only the number of files
           specified here will be transfered (chosen randmonly) and the others
           will be ignored.
    REQ:   If REQUIRED and no files are found to transfer, then an error will
           be returned
    CONV:  Run unix2dos



Credentials File
----------------

the credentials file is expected to be in the "ini" format using the server
name as the groups.  For example:

    [username@server/share]
    domain   = eastern.ewu.edu
    password = password-to-access-share

    [username@server/share]
    domain   = eastern.ewu.edu
    password = password-to-access-share

Each group key must be in the format [USERNAME@SERVER/SHARE_NAME] where:

    USERNAME:   Is the username used to connect to the Windows share.
                This will be matched against the RUSER script parameter.
    SERVER:     Is the address or hostname of the Windows server.
                This must match the RHOST script paramter
    SHARE_NAME: Is the name of the file share being served.
                This must match the first portion of the RPATH URL

The keys are:
    domain:     The domain that the username is authenticated against

    password:   The password used to connect


Examples
--------

TODO


'''

VERSION='dev'

import re
import os
import sys
import tempfile
import subprocess
import shutil
import ConfigParser
import random
from fnmatch import fnmatch
from glob import glob

def abort(msg):
    print "ERROR:", msg
    print "ABORTING"
    sys.exit(2)


def new_section(title):
    print ""
    print "--------------------------------------------------------------------"
    print title
    print "--------------------------------------------------------------------"
    print ""


#  -----------------------------------------------------------------------------
#    #####  ######  ####### ######   #####
#   #     # #     # #       #     # #     #
#   #       #     # #       #     # #
#   #       ######  #####   #     #  #####
#   #       #   #   #       #     #       #
#   #     # #    #  #       #     # #     #
#    #####  #     # ####### ######   #####
#  -----------------------------------------------------------------------------

class CredentialFileException(Exception): pass

def build_cred_group(username, server, share):
    return '%s@%s/%s' % (username.lower(), server.lower(), share.lower())

class CredentialGroup(object):
    '''Wrapper for a single group (user+server) in the credentials file'''
    def __init__(self, path, user, server, share, data):
        self.path = path        # Path to credentials file
        self.user = user
        self.server = server
        self.share = share
        self._data = data

    def _get_value(self, key, required=True, valid_values=None):
        group_key = build_cred_group(self.user, self.server, self.share)
        if self._data.has_key(key.lower()):
            value = self._data[key.lower()]
            if valid_values is not None:
                if value not in valid_values:
                    msg = "Credential group [%s] in %s has invalid value for '%s'."
                    msg += "  Valid values are: %s"
                    msg = msg % (group_key, self.path, key,
                        ", ".join(valid_values))
                    raise CredentialFileException(msg)
            return value
        elif required:
            msg = "Credential group [%s] in %s is missing required key '%s'"
            raise CredentialFileException(msg % (group_key, self.path, key))
        return None

    @property
    def password(self):
        '''User password to authenticate to SFTP server with'''
        return self._get_value('password')

    @property
    def domain(self):
        '''User password to authenticate to SFTP server with'''
        return self._get_value('domain')

class CredentialFile(object):
    '''Reader for credentials file'''

    def __init__(self, path):
        self.path = path
        self._data = self._parse_file(path)

    @staticmethod
    def _parse_file(path):
        parser = ConfigParser.RawConfigParser()
        parser.read(path)
        data = dict()
        for section in parser.sections():
            group = section.lower() # username@server/share
            data[group] = dict()
            for option in parser.options(section):
                data[group][option.lower()] = parser.get(section, option)
        return data

    def get_group(self, user, server, share):
        group_key = build_cred_group(user, server, share)
        if self._data.has_key(group_key):
            return CredentialGroup(
                path=self.path,
                user=user,
                server=server,
                share=share,
                data=self._data[group_key])

        msg = "No credentials found for [%s] in %s" % (group_key, self.path)
        raise CredentialFileException(msg)


#  -----------------------------------------------------------------------------
#      #    ######   #####  #     # #     # ####### #     # #######  #####
#     # #   #     # #     # #     # ##   ## #       ##    #    #    #     #
#    #   #  #     # #       #     # # # # # #       # #   #    #    #
#   #     # ######  #  #### #     # #  #  # #####   #  #  #    #     #####
#   ####### #   #   #     # #     # #     # #       #   # #    #          #
#   #     # #    #  #     # #     # #     # #       #    ##    #    #     #
#   #     # #     #  #####   #####  #     # ####### #     #    #     #####
#  -----------------------------------------------------------------------------


class ScriptArgumentError(Exception): pass

class ScriptArguments(object):
    '''Accessing the script's invokation arguments'''

    MODES=('GET_1', 'GET_M', 'PUT_1', 'PUT_M')
    DEL_OPTS=('DEL', 'NO_DEL')
    OVERWRITE_OPTS=('OVERWRITE', 'ERROR_EXISTING')
    MULTI_OPTS=('MULTI_OK', 'MULTI_ERROR', 'MULTI_PICK_1')
    REQ_OPTS=('REQUIRED', 'OPTIONAL')
    CONV_OPTS=('CONV', 'NO_CONV')

    def __init__(self):
        new_section("Parsing Arguments")    # Tell user

        # List all agruments by position
        print ""
        print "Args:"
        for i, arg in enumerate(sys.argv):
            print '[%02d] %s' % (i, str(arg))

        def get_sys_arg(pos, description, valid_values=None):
            '''Find and validate argument value.  Also prints out values'''

            # Argument provided?
            if len(sys.argv) <= pos:
                msg = "Missing required %s as argument %s" % (description, pos)
                raise ScriptArgumentError(msg)

            # Get value
            value = sys.argv[pos]

            # Check value is allowed
            if valid_values is not None:
                if value not in valid_values:
                    abort("Invalid value '%s' for '%s'.  Valid values are: %s" % (
                        value,
                        description,
                        ', '.join(valid_values)))

            # Tell user
            print "%-25s: %s" % (description, value)
            return sys.argv[pos]

        print ""

        self.rhost       = get_sys_arg(1, "Remote host name")
        self.ruser       = get_sys_arg(2, "Remote username")
        self.mode        = get_sys_arg(3, "Script mode", self.MODES)
        self.lpath       = get_sys_arg(4, "Local path")
        self.rpath       = get_sys_arg(5, "Remote path")
        self.cred_path   = get_sys_arg(6, "Path to credentials file")
        self.do_del      = get_sys_arg(7, "Delete file?", self.DEL_OPTS)
        self._limit      = get_sys_arg(8, "File limit")
        self.overwrite   = get_sys_arg(9, "Overwrite files?",
                                       self.OVERWRITE_OPTS)
        self.multi_act   = get_sys_arg(10, "Action if multple files",
                                       self.MULTI_OPTS)
        self.required    = get_sys_arg(11, "Required?", self.REQ_OPTS)
        self.convert     = get_sys_arg(12, "Convert File?", self.CONV_OPTS)

        # Interpret/validate limit
        if self._limit != 'ALL':
            try:
                limit = int(limit)
            except:
                msg = "LIMIT must be ALL or an integer"
                raise ScriptArgumentError(msg)

        # Sanity Check: Credentials file exists
        if not os.path.exists(self.cred_path):
            msg = "Credentials file %s does not exist" % (self.cred_path)
            raise ScriptArgumentError(msg)

        # Tell user about path interpretations
        def print_path(desc, value):
            if value is None:
                value = '--'
            print "%-25s: %s" % (desc, value)
        new_section("Paths")
        print_path("Local Directory",   self.local_dir_path)
        print_path("Local File Spec",   self.local_filename)
        print_path("Remote Share",      self.remote_share_name)
        print_path("Remote Directory",  self.remote_dir_path)
        print_path("Remote File Spec",  self.remote_filename)

        # Validate local directory exists
        if not os.path.exists(self.local_dir_path):
            msg = "Local directory %s doesn't exist" % (self.local_dir_path)
        elif not os.path.isdir(self.local_dir_path):
            abort("Local path %s is not a folder" % (self.local_dir_path))

        # Check mode specific parameter restrictions
        def mode_requires(desc, value, expected):
            if value != expected:
                msg = "For mode %s, %s must be %s (not %s)"
                msg = msg % (self.mode, desc, expected, value)
                raise ScriptArgumentError(msg)
        def mode_restricts(desc, value, invalid_value):
            if value == invalid_value:
                msg = "For mode %s, '%s' is not valid for %s"
                msg = msg % (self.mode, value, desc)
                raise ScriptArgumentError(msg)
        if self.mode in ('GET_1', 'PUT_1'):
            mode_restricts("MULTI", self.multi_act, 'MULTI_OK')
            mode_requires("LIMIT", self._limit, 'ALL')
            mode_requires("REQ", self.required, 'REQUIRED')
        if self.mode in ('GET_M', 'PUT_M'):
            mode_requires("MULTI", self.multi_act, 'MULTI_OK')

        # Load credentials
        self.creds = CredentialFile(self.cred_path)
        self.creds = self.creds.get_group(self.ruser, self.rhost,
                                          self.remote_share_name)

    @property
    def limit(self):
        if self._limit == 'ALL':
            return None
        return int(self._limit)

    @staticmethod
    def _split_path(path, sep='/'):
        '''Split path into dirpath and basename'''
        path = path.replace('\\', '/')
        parts = path.split("/")
        if len(parts) == 0:
            return ('.', None)
        elif len(parts) == 1:
            return ('.', parts[0])
        else:
            return (sep.join(parts[:-1]), parts[-1])

    @property
    def _local_path_parts(self):
        '''Separate lpath into directory and filename'''
        # LPATH is full path to file
        if self.mode in ('GET_1', 'PUT_1', 'PUT_M'):
            dir_path, filename = self._split_path(self.lpath)
            return dir_path, filename
        # LPATH is path to a directory (GET_M)
        else:
            return self.lpath, None

    @property
    def local_dir_path(self):
        '''Path to directory on local host to operate in'''
        return self._local_path_parts[0]

    @property
    def local_filename(self):
        '''Name of file(s) on local host to operate on'''
        return self._local_path_parts[1]

    @property
    def _remote_path_parts(self):
        '''Seperate rpath into share, directory, and filename'''
        # Remove leading slash if present
        rpath = self.rpath.replace("\\", '/')
        while rpath.startswith('/'):
            rpath = rpath[1:]

        # RPATH is full path to file:
        if self.mode in ('GET_1', 'GET_M', 'PUT_1'):
            dir_path, filename = self._split_path(rpath)
        # RPATH is path to a directory (PUT_M)
        else:
            dir_path, filename = rpath.replace("\\", '/'), None

        # Seperate out share name
        parts = dir_path.split("/")
        if len(parts) == 1:
            share = parts[0]
            dir_path = '.'
        else:
            share = parts[0]
            dir_path = '/'.join(parts[1:])

        return share, dir_path, filename

    @property
    def remote_share_name(self):
        '''Path to directory on remote host to operate in'''
        return self._remote_path_parts[0]

    @property
    def remote_dir_path(self):
        '''Path to directory on remote host to operate in'''
        return self._remote_path_parts[1].replace("/", "\\")

    @property
    def remote_filename(self):
        '''Name of file(s) on remote host to operate on'''
        return self._remote_path_parts[2]


#  -----------------------------------------------------------------------------
#    #####   #     #  ######
#   #     #  ##   ##  #     #
#   #        # # # #  #     #
#    #####   #  #  #  ######
#         #  #     #  #     #
#   #     #  #     #  #     #
#    #####   #     #  ######
#  -----------------------------------------------------------------------------

class SmbClientError(Exception): pass

class SmbClient(object):
    '''Wrapper for executing smbclient program'''

    PATH='/usr/bin/smbclient'

    def __init__(self, script_args):
        self._args = script_args

        # Sanity Check: smbclient exists
        if not os.path.exists(self.PATH):
            msg = "%s does not exists.  smbclient not installed?"
            raise Exception(msg % (self.PATH))

    def execute(self, cmds, write_output=None):
        '''Execute smbclient with the given commands'''

        # Create file to hold smbclient credentials
        prefix = os.path.basename(sys.argv[0]) + '.'
        cred_path = tempfile.mkstemp(prefix=prefix)[1]

        try:
            args = self._args
            creds = self._args.creds

            # Write credentials to smbclient format
            fh = open(cred_path, 'wt')
            print >>fh, 'username = %s' % (args.ruser)
            print >>fh, 'domain   = %s' % (creds.domain)
            print >>fh, 'password = %s' % (creds.password)
            fh.close()

            # Craft smbclient commands
            cmd = '; '.join(cmds)

            # Supress prompting
            cmd = 'prompt; ' + cmd

            # cd to server directory
            cmd = "cd %s; " % (args.remote_dir_path) + cmd

            # Run smbclient
            if write_output is None:
                write_output = sys.stdout
            cmd = [self.PATH,
                r'\\%s\%s' % (args.rhost, args.remote_share_name),
                '-A', cred_path,
                '-c', cmd]
            print "$>", " ".join(cmd)
            rtn_code = subprocess.call(
                args=cmd,
                stdout=write_output,
                stderr=write_output)
            if rtn_code != 0:
                raise SmbClientError("smbclient returned code " + str(rtn_code))

        finally:
            # Clean up script
            os.unlink(cred_path)

    LIST_PAT=re.compile(r'^  (\S.*?)\s([DAHS]+)?\s*\d+  \w{3} \w{3}\s+\d+\s+\d+:\d+:\d+ \d{4}$')

    def list_remote_files(self, filepat):
        '''Execute the /usr/bin/lftp program and list files'''

        # Create file to hold file list in
        prefix = os.path.basename(sys.argv[0]) + '.'
        list_file = tempfile.mkstemp(prefix=prefix)[1]
        files = list()

        try:
            fh = open(list_file, "wt")
            self.execute(('ls %s' % (filepat), ), fh)
            fh.close()

            # Read files listed
            fh = open(list_file, 'rt')
            for line in fh.readlines():
                line = line.rstrip()

                # Check for invalid directory error
                if 'NT_STATUS_OBJECT_NAME_NOT_FOUND' in line:
                    msg = "Directory does not exist: "
                    raise SmbClientError(msg + self._args.remote_dir_path)

                # Interpret file listing line
                m = self.LIST_PAT.match(line)
                print ">", line.rstrip().ljust(80),
                if not m:
                    print "[ignored]"

                else:
                    filename = m.group(1).strip()
                    file_type = m.group(2)  # D: Directory.  May be blank
                    if file_type is None:
                        file_type = ''

                    if 'D' in file_type:
                        print "[directory]"

                    else:
                        # smbclient seems to not match filename patterns well
                        if fnmatch(filename, filepat):
                            print "[file]"
                            files.append(filename)
                        else:
                            print "[file:nomatch]"

            fh.close()

        finally:
            os.unlink(list_file)

        return files


#  -----------------------------------------------------------------------------
#   #     #    #    ### #     #
#   ##   ##   # #    #  ##    #
#   # # # #  #   #   #  # #   #
#   #  #  # #     #  #  #  #  #
#   #     # #######  #  #   # #
#   #     # #     #  #  #    ##
#   #     # #     # ### #     #
#  -----------------------------------------------------------------------------


if __name__ == '__main__':

    print "Running %s - Version %s" % (sys.argv[0], VERSION)

    try:

        # Parse commandline arguments
        args = ScriptArguments()

        # Init smbclient wrapper
        smbclient = SmbClient(args)

        # Ensure that we're in the local directory
        print "Invoked in", os.getcwd()
        os.chdir(args.local_dir_path)
        print "Working in", args.local_dir_path

        # List files on remote site
        filepat = '*'
        if args.remote_filename is not None:
            filepat = args.remote_filename
        msg = "Listing %s files in %s:%s"
        new_section(msg % (filepat, args.rhost, args.remote_dir_path))
        remote_files = smbclient.list_remote_files(filepat)
        print "\n%d files found" % (len(remote_files))

        # List files on local host
        filepat = '*'
        if args.local_filename is not None:
            filepat = args.local_filename
        new_section("Listing %s files in %s" % (filepat, args.local_dir_path))
        local_files = list()
        for path in glob(os.path.join(args.local_dir_path, filepat)):
            local_files.append(os.path.basename(path))
        for filename in local_files:
            print filename
        print "\n%d files found" % (len(local_files))

        # Select files to operate on
        new_section("Selecting files to transfer")
        if args.mode in ('GET_1', 'GET_M'):
            selected = remote_files[:]
        if args.mode in ('PUT_1', 'PUT_M'):
            selected = local_files[:]

        # Handle multiple files
        if len(selected) > 1:
            if args.multi_act == 'MULTI_ERROR':
                abort ("Multiple files match pattern")
            elif args.multi_act == 'MULTI_PICK_1':
                selected = [random.choice(selected), ]

        # Show user which files
        for filename in selected:
            print filename
        print "\n%d files selected" % (len(selected))

        # Handle no files
        if len(selected) == 0:
            if args.required == 'REQUIRED':
                abort("No files found to transfer")
            else:
                print "No files found to transfer"

        # Perform transfers
        if len(selected) > 0:
            new_section("Transferring files")
        for filename in selected:
            if args.mode in ('GET_1', 'GET_M'):

                # Determine filename to save file as
                if args.mode == 'GET_1':
                    target_filename = args.local_filename
                elif args.mode == 'GET_M':
                    target_filename = filename

                remote_full_path = "\\\\%s\\%s\\%s\\%s" % (
                    args.rhost, args.remote_share_name, args.remote_dir_path,
                    filename)

                local_full_path = os.path.join(args.local_dir_path,
                                               target_filename)

                print "%s -> %s" % (remote_full_path, local_full_path)

                # Check existing
                if args.overwrite == 'ERROR_EXISTING':
                    if target_filename in local_files:
                        msg = "File already exists on local host: "
                        abort(msg + local_full_path)

                # Perform transfer
                cmds = list()
                cmds.append('get "%s" "%s"' % (filename, target_filename))
                if args.do_del == 'DEL':
                    cmds.append('rm "%s"' % (filename))
                smbclient.execute(cmds)

                # Do file conversion
                if args.convert == 'CONV':
                    print "dos2unix:", local_full_path
                    rtn_code = subprocess.call(
                        args=['/usr/bin/dos2unix', '-v', local_full_path],
                        stdout = sys.stdout,
                        stderr = sys.stderr,
                        )
                    if rtn_code != 0:
                        abort("dos2unix return code %d" % (rtn_code))

                # Remind user we deleted the file
                print "deleted %s" % (remote_full_path)


            elif args.mode in ('PUT_1', 'PUT_M'):

                # Determine filename to save file as
                if args.mode == 'PUT_1':
                    target_filename = args.remote_filename
                elif args.mode == 'PUT_M':
                    target_filename = filename

                remote_full_path = "\\\\%s\\%s\\%s\\%s" % (
                    args.rhost, args.remote_share_name, args.remote_dir_path,
                    target_filename)

                local_full_path = os.path.join(args.local_dir_path,
                                               filename)

                print "%s -> %s" % (local_full_path, remote_full_path)

                # Check existing
                if args.overwrite == 'ERROR_EXISTING':
                    if target_filename in remote_files:
                        abort("File already exists: " + remote_full_path)

                # Do file conversion
                if args.convert == 'CONV':
                    print "unix2dos:", local_full_path
                    rtn_code = subprocess.call(
                        args=['/usr/bin/unix2dos', '-v', local_full_path],
                        stdout = sys.stdout,
                        stderr = sys.stderr,
                        )
                    if rtn_code != 0:
                        abort("unix2dos return code %d" % (rtn_code))

                # Perform transfer
                cmds = list()
                cmds.append('put "%s" "%s"' % (filename, target_filename))
                smbclient.execute(cmds)
                if args.do_del == 'DEL':
                    path = os.path.join(args.local_dir_path, filename)
                    try:
                        print "deleting", path
                        os.unlink(path)
                    except OSError, e:
                        abort ("Failed to delete %s: %s" % (path, str(e)))

            print "" # After file spacer

    except ScriptArgumentError, e:
        abort("Usage Error: " + str(e))

    except CredentialFileException, e:
        abort("Credentials Error: " + str(e))

    except SmbClientError, e:
        abort(str(e))

    new_section("Finished")
