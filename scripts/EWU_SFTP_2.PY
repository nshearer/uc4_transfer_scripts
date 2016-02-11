#!/usr/bin/python
'''
EWU_SFTP_2.PY - Generic Shell to Perform SFTP Transfers

Written by Nathan Shearer


Summary
-------

This script uses /usr/bin/lftp to perform file transfers to or from an SFTP
server.  It is intended to be called by an AppWorx module named EWU_SFTP_2.
This script can be used to perform both password based and key file based
authentication.

Modes
-----

This script is intended to solve multiple use cases.  Use the MODE parameter
to specify the use case.

    GET_1   - Get 1 file from a remote SFTP server to local host
    GET_M   - Get multiple files from a remote SFTP server to this local host
    PUT_1   - Put 1 files from this local host to a remote SFTP server
    PUT_M   - Put multiple files from this local host to a remote SFTP server


Parameters
----------

Here are the names and general explanations of the script parameters.  Many
parameters have different uses depending on the mode value.  Specific meanings
for each mode are listed below this section.

 [ 1] RHOST: The remote host (either resolvable name or IP address)
 [ 2] RUSER: Username to use for connecting to remote host
 [ 3] MODE:  Mode of operation (GET_1, GET_M, PUT_1, PUT_M)
 [ 4] LPATH: Path to local folder or file
 [ 5] RPATH: Path to remote folder or file
 [ 6] CREDS: Path to the credentials file.  See below for syntax.
 [ 7] DEL:   Delete on success? (DEL or NO_DEL)
 [ 8] LIMIT: Limit number of files retrieved, or ALL
 [ 9] OVERW: Overwrite existing files? (OVERWRITE or ERROR_EXISTING)
 [10] MULTI: Action if multiple files match (MULTI_OK, MULTI_ERROR, or MULTI_PICK_1)
 [11] REQ:   What to do if no files are found (REQUIRED or OPTIONAL)

Note on wildcards:
    Sometimes paramters accept wildcards (path globbing) where * matches any
    sequence of characters and ? matches any single character.

    WARNING:
      - You should always quote field values with wildcards with single quotes
        to prevent wildcard expansion by UC4 when this script is being called.
      - Wildcards can only be used for filenames, not directories

For GET_1 mode:
    LPATH: Is the path to save the file to on the local host including filename.
           Use filename '(remote_filename)' to use the name of file found on the
           remote server.  Example: /data/(remote_filename)
    RPATH: Is the path to the file on the remote host to copy the file from
           including the filename.  Wildcards may be used if the remote filename
           is not known.
    MULTI: If the filename pattern in RPATH matches multiple files and
           MULTI=MULTI_ERROR, then the script will error without copying any
           files.  Otherwise, one file will be chosen randomly to be copied.
           MULTI_OK value not allowed in this mode.
    DEL:   If DEL, then the file copied on the remote SFTP server will be
           deleted if the transfer succeeds.
    LIMIT: Must be ALL for this mode
    REQ:   Must be REQUIRED for this mode

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

For PUT_1 mode:
    LPATH: Is the path to the file on the local host to push up including
           the filename.  Wildcards may be used if local filename is not known.
    RPATH: Is the full path to the file on the remote host to place the file
           including the filename.
           Use filename '(local_filename)' to use the name of file found on the
           local server.  Example: /data/(local_filename)
    MULTI: If the filename pattern in LPATH matches multple files, and this
           value is MULTI_ERROR, then an error code will be returned.  If
           value is MULTI_PCIK_1, then one of the matching files will be chosen
           at random to send.
           Value MULTI_OK is not allowed for this mode.
    DEL:   If DEL, then each file successfully copied will be deleted from the
           local host.
    LIMIT: Must be ALL for this mode
    REQ:   Must be REQUIRED for this mode

For PUT_M mode:
    LPATH: Is the path to the files on the local host to push up including a
           filename pattern with wildcards.
    RPATH: Is the path to the directory on the remote SFTP server to copy files
           to.
    MULTI: Must be MULTI_OK for this mode
    DEL:   If DEL, then each file successfully copied will be deleted from the
           local host.
    LIMIT: If ALL, then copy all files found.  Else, only the number of files
           specified here will be transfered (chosen randmonly) and the others
           will be ignored.
    REQ:   If REQUIRED and no files are found to transfer, then an error will
           be returned

Credentials File
----------------

the credentials file is expected to be in the "ini" format using the server
name as the groups.  For example:

    [my_username@my.server.com]
    method = password
    password = my_password
    server_key = ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA...

    [my_username@my.server.com]
    method = keyfile
    keyfile = /path/to/private/key
    server_key = ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABA...

Each group key must be in the format [USERNAME@SERVER] where:

    USERNAME: Is the username used to connect to the SFTP server.
              This will be matched against the RUSER script parameter.
    SERVER:   Is the address or hostname of the SFTP server.
              This must match the RHOST script paramter

The keys are:
    method      Either password or keyfile

    password:   If method=password, then use this password to authenticate

    keyfile:    If method=keyfile, then use this private SSH keyfile
                The paired public keyfile must be regiested on the remote SFTP
                server for this user to allow authentication.
                Often, you'll want to have the DataCenter place this keyfile in
                a more secure location such as in /home/appworx/.ssh/

    server_key: Is the public key that authenticates the remote server.
                This is used to provide a level of security that verifies that
                we're connecting to the expected SFTP server, preventing
                man in the middle attackes.  This is part of the normal SFTP
                authentication process.

                When copying the key to this line, include "ssh-rsa" an
                everything to the end of the line.

                To find the public key of a server, use the command:
                    ssh-keyscan -H -t rsa,dsa my_server
                    (Use last line)

                To disable server key verification (NOT RECOMENDED), use the
                value "disabled"


Examples
--------

TODO


Why Python?
-----------

This script is written in Python to make handling the passwords more secure.
I found it very difficult to work with the passwords from the credentials file
without echo'ing them.

echo "$PASSWORD" >> except_file causes password to be visible by the ps command
for a short time.

'''
VERSION='dev'

import os
import sys
import tempfile
import subprocess
import shutil
import ConfigParser
import random
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

class CredentialGroup(object):
    '''Wrapper for a single group (user+server) in the credentials file'''
    def __init__(self, path, user, server, data):
        self.path = path
        self.user = user
        self.server = server
        self._data = data

    def _get_value(self, key, required=True, valid_values=None):
        group_key = "%s@%s" % (self.user, self.server)
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
    def auth_mode(self):
        '''Mode of authentication'''
        return self._get_value('method', valid_values=('keyfile', 'password'))

    @property
    def password(self):
        '''User password to authenticate to SFTP server with'''
        if self.auth_mode == 'password':
            return self._get_value('password')
        else:
            raise Exception("Invalid auth mode")

    @property
    def keyfile_path(self):
        '''Path to keyfile to use to authenticate to SFTP server with'''
        if self.auth_mode == 'keyfile':
            return self._get_value('keyfile')
        else:
            raise Exception("Invalid auth mode")

    @property
    def server_key(self):
        value = self._get_value('server_key')
        if value.lower() == 'disabled':
            return None
        return value

    @property
    def server_key_check_enabled(self):
        return self.server_key is not None


class CredentialFile(object):
    '''Reader for credentials file'''

    def __init__(self, path):
        self.path = path
        self._data = self._parse_file(path)

    @staticmethod
    def _parse_file(path):
        # Check file exists
        if not os.path.exists(path):
            msg = "Credential file %s doesn't exist" % (path)
            raise CredentialFileException(msg)

        # Check that credential file is readable
        try:
            fh = open(path, 'rt')
            fh.read()
        except Exception, e:
            msg = "Can't read credential file at %s" % (path)
            raise CredentialFileException(msg)

        # Parse credential file
        try:
            parser = ConfigParser.RawConfigParser()
            parser.read(path)
            data = dict()
            for section in parser.sections():
                group = section.lower() # username@server
                data[group] = dict()
                for option in parser.options(section):
                    data[group][option.lower()] = parser.get(section, option)
            return data
        except Exception, e:
            msg = "Unable to parse credential file %s" % (path)
            msg += "\nCheck that file is in standard 'ini' format."
            msg += "\n(file contents hidden to keep secrets)"
            raise CredentialFileException(msg)

    def get_group(self, user, server):
        group_key = ('%s@%s' % (user, server)).lower()
        if self._data.has_key(group_key):
            return CredentialGroup(
                path=self.path,
                user=user,
                server=server,
                data=self._data[group_key])

        msg = "No credentials found for %s in %s" % (group_key, self.path)
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

    def __init__(self):
        new_section("Parsing Arguments")    # Tell user

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
        self.creds = self.creds.get_group(self.ruser, self.rhost)

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
        '''Seperate rpath into directory and filename'''
        # RPATH is full path to file:
        if self.mode in ('GET_1', 'GET_M', 'PUT_1'):
            dir_path, filename = self._split_path(self.rpath)
            return dir_path, filename
        # RPATH is path to a directory (PUT_M)
        else:
            return self.rpath, None

    @property
    def remote_dir_path(self):
        '''Path to directory on remote host to operate in'''
        return self._remote_path_parts[0]

    @property
    def remote_filename(self):
        '''Name of file(s) on remote host to operate on'''
        return self._remote_path_parts[1]


#  -----------------------------------------------------------------------------
#    #####  ####### ####### ######
#   #     # #          #    #     #
#   #       #          #    #     #
#    #####  #####      #    ######
#         # #          #    #
#   #     # #          #    #
#    #####  #          #    #
#  -----------------------------------------------------------------------------

class SftpError(Exception): pass

class LftpClient(object):
    '''Wrapper for executing /usr/bin/lftp'''

    PATH='/usr/bin/lftp'

    def __init__(self, script_args):
        self._args = script_args

        # Sanity Check: lftp exists
        if not os.path.exists(self.PATH):
            msg = "%s does not exists.  lftp not installed?"
            raise Exception(msg % (self.PATH))

    def execute(self, cmds):
        '''Execute lftp with the given commands'''

        # Create file to hold lftp instructions
        prefix = os.path.basename(sys.argv[0]) + '.'
        script_path = tempfile.mkstemp(prefix=prefix)[1]

        try:
            # Create lftp script
            fh = open(script_path, 'wt')

            args = self._args
            creds = self._args.creds

            # Craft ssh command to use
            sftp_cmd = "ssh -a -x"
            if creds.auth_mode == 'keyfile':
                if creds.keyfile_path is not None:
                    sftp_cmd += " -i %s" % (creds.keyfile_path)
            if creds.server_key_check_enabled:
                sftp_cmd += " -o StrictHostKeyChecking=yes"
            else:
                sftp_cmd += " -o StrictHostKeyChecking=no"
            print >>fh, 'set sftp:connect-program "%s"' % (sftp_cmd)

            # Craft connection command
            if creds.auth_mode == 'keyfile':
                print >>fh, 'open -u %s, sftp://%s' % (args.ruser, args.rhost)
            elif creds.auth_mode == 'password':
                print >>fh, 'open -u %s,"%s" sftp://%s' % (
                    args.ruser, creds.password, args.rhost)

            # Allow file overwrite
            if args.overwrite == 'OVERWRITE':
                print >>fh, 'set xfer:clobber true'

            # Change to remote working directory
            if args.remote_dir_path != '.':
                print >>fh, 'cd "%s"' % (args.remote_dir_path)

            # Change to local working directory
            if args.local_dir_path is not None:
                if args.local_dir_path != '.':
                    print >>fh, 'lcd "%s"' % (args.local_dir_path)

            # Execute commands
            for line in cmds:
                print >>fh, line

            fh.close()

            # DEBUG Script file
            # print "--- Script file ---"
            # fh = open(script_path, 'rt')
            # print fh.read().strip()
            # fh.close()
            # print "-------------------"

            # Run lftp
            rtn_code = subprocess.call(
                args=[self.PATH, '-f', script_path],
                stdout=sys.stdout,
                stderr=sys.stdout)
            if rtn_code != 0:
                raise SftpError("lftp returned code " + str(rtn_code))

        finally:
            # Clean up script
            os.unlink(script_path)

    def list_remote_files(self, filepat):
        '''Execute the /usr/bin/lftp program and list files'''

        # Create file to hold file list in
        prefix = os.path.basename(sys.argv[0]) + '.'
        list_file = tempfile.mkstemp(prefix=prefix)[1]
        files = list()

        try:
            cmd = [
                'cls -1 "%s" > %s' % (filepat, list_file)
                ]
            self.execute(cmd)

            # Read files listed
            fh = open(list_file, 'rt')
            for line in fh.readlines():
                filename = line.strip()
                if filename not in ['.', '..']:
                    if filename[-1] != '/':
                        files.append(filename)
            fh.close()

        finally:
            os.unlink(list_file)

        return files


#  -----------------------------------------------------------------------------
#   #     #                        #    #
#   #     #  ####   ####  #####    #   #  ###### #   #  ####
#   #     # #    # #        #      #  #   #       # #  #
#   ####### #    #  ####    #      ###    #####    #    ####
#   #     # #    #      #   #      #  #   #        #        #
#   #     # #    # #    #   #      #   #  #        #   #    #
#   #     #  ####   ####    #      #    # ######   #    ####
#  -----------------------------------------------------------------------------

def known_hosts_path():
    home = os.path.expanduser("~")
    path = os.path.join(home, '.ssh', 'known_hosts')
    if not os.path.exists(path):
        raise Exception("Can't find known_hosts file")
    return path


def get_host_key(hostname):
    '''Get the host/server key for this server from known_hosts'''
    cmd = [
        '/usr/bin/ssh-keygen',
        '-H',
        '-F', hostname,
        ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.wait()
    stdout = p.stdout.read()
    stderr = p.stderr.read()

    if p.returncode != 0:
        e = stdout + "\n" + stderr
        abort("Failed to query known_hosts with ssh-keygen: " + e)

    for line in stdout.split("\n"):
        if len(line) > 0:
            if line[0] != '#':
                parts = line.split(' ')
                if len(parts) > 2:
                    if parts[-2] == 'ssh-rsa':
                        return ' '.join(parts[-2:])

    return None


def remove_host_key(hostname):
    '''Remove a host key'''
    cmd = [
        '/usr/bin/ssh-keygen',
        '-R', hostname,
        ]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    p.wait()
    stdout = p.stdout.read()
    stderr = p.stderr.read()

    if p.returncode != 0:
        e = stdout + "\n" + stderr
        msg = "Failed to remove entry for %s from known_hosts with ssh-keygen:"
        abort(msg + " " + e)


def add_host_key(hostname, key):
    '''Add a host key to known_hosts'''
    fh = open(known_hosts_path(), 'at')
    print >>fh, "%s %s" % (hostname, key)
    fh.close()


#  -----------------------------------------------------------------------------
#   #     #    #    ### #     #
#   ##   ##   # #    #  ##    #
#   # # # #  #   #   #  # #   #
#   #  #  # #     #  #  #  #  #
#   #     # #######  #  #   # #
#   #     # #     #  #  #    ##
#   #     # #     # ### #     #
#  -----------------------------------------------------------------------------


KEEP_FILENAME_TOKENS=('(remote_filename)', '(local_filename)', '(keep)')

if __name__ == '__main__':

    try:

        # Parse commandline arguments
        args = ScriptArguments()
        print "%s version %s" % (os.path.basename(sys.argv[0]), VERSION)

        # Init LFTP wrapper
        sftp = LftpClient(args)

        # Check Host key
        new_section("Checking host key for " + args.rhost)

        if args.creds.server_key != 'disabled':

            print "\nknown_hosts path: " + os.path.abspath(known_hosts_path())

            existing_key = get_host_key(args.rhost)
            print "\nExisting key: " + str(existing_key)

            print "\nExpected key: " + str(args.creds.server_key)

            if existing_key is None:
                print "\nKey not in known_hosts.  Adding"
                add_host_key(args.rhost, args.creds.server_key)

            elif existing_key != args.creds.server_key:
                print "\nKeys do not match.  Updating."

                print "Removing existing key"
                remove_host_key(args.rhost)

                print "Adding expected key"
                add_host_key(args.rhost, args.creds.server_key)

            else:
                print "Keys match"


        else:
            print "SERVER KEY CHECKING DISABLED"

        # List files on remote site
        filepat = '*'
        if args.remote_filename is not None and args.remote_filename not in KEEP_FILENAME_TOKENS:
            filepat = args.remote_filename
        msg = "Listing %s files in %s:%s"
        new_section(msg % (filepat, args.rhost, args.remote_dir_path))
        remote_files = sftp.list_remote_files(filepat)
        for filename in remote_files:
            print filename
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
                    # Target filename '(remote_filename)' means keep origional filename
                    if target_filename in KEEP_FILENAME_TOKENS:
                        target_filename = filename
                elif args.mode == 'GET_M':
                    target_filename = filename
                print "%s@%s/%s/%s -> %s/%s" % (
                    args.ruser, args.rhost, args.remote_dir_path, filename,
                    args.local_dir_path, target_filename)

                # Check existing (lftp will error anyways, but we can give
                # a more useful error message)
                if args.overwrite == 'ERROR_EXISTING':
                    if target_filename in local_files:
                        path = os.path.join(args.local_dir_path,target_filename)
                        abort("File already exists on local host: " + path)

                # Perform transfer
                cmds = list()
                cmds.append('get "%s" "%s"' % (filename, target_filename))
                if args.do_del == 'DEL':
                    cmds.append('rm "%s"' % (filename))
                sftp.execute(cmds)

                # Remind user we deleted the file
                print "deleted %s@%s/%s/%s" % (
                    args.ruser, args.rhost, args.remote_dir_path, filename)

            elif args.mode in ('PUT_1', 'PUT_M'):

                # Determine filename to save file as
                if args.mode == 'PUT_1':
                    target_filename = args.remote_filename
                    # Target filename '(local_filename)' means keep origional filename
                    if target_filename in KEEP_FILENAME_TOKENS:
                        target_filename = filename
                elif args.mode == 'PUT_M':
                    target_filename = filename
                print "%s/%s -> %s@%s/%s/%s" % (
                    args.local_dir_path, filename,
                    args.ruser, args.rhost, args.remote_dir_path, target_filename)

                # Check existing (lftp will error anyways, but we can give
                # a more useful error message)
                if args.overwrite == 'ERROR_EXISTING':
                    if target_filename in remote_files:
                        path = os.path.join(args.remote_dir_path,target_filename)
                        abort("File already exists on sftp server host: " + path)

                # Perform transfer
                cmds = list()
                cmds.append('put "%s" "%s"' % (filename, target_filename))
                sftp.execute(cmds)
                if args.do_del == 'DEL':
                    path = os.path.join(args.local_dir_path, filename)
                    try:
                        print "deleting", path
                        os.unlink(path)
                    except OSError, e:
                        abort ("Failed to delete %s: %s" % (path, str(e)))

    except ScriptArgumentError, e:
        abort("Usage Error: " + str(e))

    except CredentialFileException, e:
        abort("Credentials Error: " + str(e))

    except SftpError, e:
        abort(str(e))

    new_section("Finished")
