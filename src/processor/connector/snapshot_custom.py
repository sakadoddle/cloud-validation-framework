"""Common file for running validator functions."""
# 1) github
# 1a) private
# HTTP - https://github.com/ajeybk/mytest.git
# username - kbajey@gmail.com or ajeybk
# password - prompt and env variable or form in the https url
# SSH - git@github.com:ajeybk/mytest.git
# identity file for host - /home/ajey/ssh_working/id_rsa_bitbucket

# 1b) public
# HTTP - https://github.com/prancer-io/cloud-validation-framework.git
# username - kbajey@gmail.com or ajeybk
# password - should not prompt, even if passed should work in url or from env variable, should work
# SSH - git@github.com:prancer-io/cloud-validation-framework.git
# identity file for host - /home/ajey/ssh_working/id_rsa_bitbucket

# 2) gitlab
# 2a) private
# HTTP - https://gitlab.com/tsdeepak/ulic_backend.git
# username - kbajey@gmail.com or kbajey
# password - prompt and env variable or form in the https url
# SSH - git@gitlab.com:kbajey/myrepo.git
# identity file for host - /home/ajey/ssh_working/id_rsa_bitbucket

# 2b) public
# HTTP - https://gitlab.com/kbajey/myrepo.git
# username - kbajey@gmail.com or kbajey
# password - prompt and env variable or form in the https url
# SSH - git@gitlab.com:kbajey/myrepo.git
# identity file for host - /home/ajey/ssh_working/id_rsa_bitbucket


# 3) bitbucket
# 3a) private
# HTTP - https://ajeybk@bitbucket.org/ajeybk/azframework.git
# username - kbajey@gmail.com or ajeybk
# password - prompt and env variable or form in the https url
# SSH - git@bitbucket.org:ajeybk/azframework.git
# identity file for host - /home/ajey/ssh_working/id_rsa_bitbucket

# 3b) public
# HTTP - https://ajeybk@bitbucket.org/ajeybk/aws-cli.git
# HTTP - https://ajeybk@bitbucket.org/ajeybk/mytestpub.git
# username - kbajey@gmail.com or ajeybk
# password - prompt and env variable or form in the https url
# SSH - git@bitbucket.org:ajeybk/aws-cli.git
# SSH - git@bitbucket.org:ajeybk/mytestpub.git
# identity file for host - /home/ajey/ssh_working/id_rsa_bitbucket

# 4) visualstudio
# 4a) private
# HTTP - https://ebizframework.visualstudio.com/whitekite/_git/whitekite
# HTTP - https://ajey.khanapuri%40liquware.com@ebizframework.visualstudio.com/whitekite/_git/whitekite
# username - ajey.khanapuri@liquware.com
# password - prompt and env variable or form in the https url
# SSH - Ebizframework@vs-ssh.visualstudio.com:v3/Ebizframework/whitekite/whitekite
# identity file for host - /home/ajey/ssh_working/id_rsa_azure
# 4b) public



#### Algorithm
# Add a attribute 'sshhost' : 'vs-ssh.visualstudio.com' or 'bitbucket.org' or 'gitlab.com' or 'github.com'
# Add a attribute 'sshuser': 'git' # All git servers expect 'git' as the user, but if there is an exception
# Add a attribute 'private': true|false
# For backward compatability it is assumed to be true.
# If giturl starts with https://, it is https based access otherwise ssh based access.

# For https public repo, username and password do not harm.
# For private https repo, read username from connector, if not present ignore.
# For https private repo, if username given, then read user_secret from connector, if present use,
# then check env variable, then prompt only

# For public ssh repo, ssh_key_file has to be present.
# Public repo clone with ssh_key_file does not require ssh/config file, whereas StrictHostKeyChecking=no
# may be required so that the user prompt may come up if githost is not present in known hosts.
# For private ssh repo with ssh_key_file, ssh/config file has to be created using 'sshhost', 'sshuser',
#  'ssh_key_file'
# Host <sshhost>
#   HostName <sshhost>
#   User <sshuser>
#   IdentityFile <ssh_key_file>
#
# Host *
#   IdentitiesOnly yes
#   ServerAliveInterval 100
import json
import hashlib
import time
import tempfile
import shutil
import hcl
import re
import os
import glob
import copy
from subprocess import Popen, PIPE
import urllib.parse
from git import Repo
from git import Git
from processor.helper.file.file_utils import exists_file, exists_dir, mkdir_path, remove_file
from processor.logging.log_handler import getlogger
from processor.connector.vault import get_vault_data
from processor.helper.json.json_utils import get_field_value, json_from_file,\
    collectiontypes, STRUCTURE, get_field_value_with_default
from processor.helper.config.config_utils import config_value, get_test_json_dir
from processor.helper.config.rundata_utils import get_from_currentdata
from processor.database.database import insert_one_document, sort_field, get_documents,\
    COLLECTION, DATABASE, DBNAME
from processor.helper.httpapi.restapi_azure import json_source
from processor.connector.snapshot_utils import validate_snapshot_nodes


logger = getlogger()

def convert_to_json(file_path, node_type):
    json_data = {}
    if node_type == 'json':
        json_data = json_from_file(file_path, escape_chars=['$'])
    elif node_type == 'terraform':
        with open(file_path, 'r') as fp:
            json_data = hcl.load(fp)
    else:
        logger.error("Snapshot error type:%s and file: %s", node_type, file_path)
    return json_data


def get_custom_data(snapshot_source):
    sub_data = {}
    if json_source():
        dbname = config_value(DATABASE, DBNAME)
        collection = config_value(DATABASE, collectiontypes[STRUCTURE])
        parts = snapshot_source.split('.')
        qry = {'name': parts[0]}
        sort = [sort_field('timestamp', False)]
        docs = get_documents(collection, dbname=dbname, sort=sort, query=qry, limit=1)
        logger.info('Number of Custom Documents: %d', len(docs))
        if docs and len(docs):
            sub_data = docs[0]['json']
    else:
        json_test_dir = get_test_json_dir()
        file_name = '%s.json' % snapshot_source if snapshot_source and not \
            snapshot_source.endswith('.json') else snapshot_source
        custom_source = '%s/../%s' % (json_test_dir, file_name)
        logger.info('Custom source: %s', custom_source)
        if exists_file(custom_source):
            sub_data = json_from_file(custom_source)
    return sub_data


def get_node(repopath, node, snapshot_source, ref):
    """ Fetch node from the cloned git repository."""
    collection = node['collection'] if 'collection' in node else COLLECTION
    parts = snapshot_source.split('.')
    db_record = {
        "structure": "git",
        "reference": ref,
        "source": parts[0],
        "path": node['path'],
        "timestamp": int(time.time() * 1000),
        "queryuser": "",
        "checksum": hashlib.md5("{}".encode('utf-8')).hexdigest(),
        "node": node,
        "snapshotId": node['snapshotId'],
        "collection": collection.replace('.', '').lower(),
        "json": {}
    }
    json_path = '%s/%s' % (repopath, node['path'])
    file_path = json_path.replace('//', '/')
    logger.info('File: %s', file_path)
    if exists_file(file_path):
        node_type = node['type'] if 'type' in node and node['type'] else 'json'
        json_data = convert_to_json(file_path, node_type)
        logger.info('type: %s, json:%s', node_type, json_data)
        # json_data = json_from_file(file_path)
        if json_data:
            db_record['json'] = json_data
            data_str = json.dumps(json_data)
            db_record['checksum'] = hashlib.md5(data_str.encode('utf-8')).hexdigest()
    else:
        logger.info('Get requires valid file for snapshot not present!')
    logger.debug('DB: %s', db_record)
    return db_record

def get_all_nodes(repopath, node, snapshot_source, ref):
    """ Fetch all the nodes from the cloned git repository in the given path."""
    db_records = []
    collection = node['collection'] if 'collection' in node else COLLECTION
    parts = snapshot_source.split('.')
    d_record = {
        "structure": "git",
        "reference": ref,
        "source": parts[0],
        "path": '',
        "timestamp": int(time.time() * 1000),
        "queryuser": "",
        "checksum": hashlib.md5("{}".encode('utf-8')).hexdigest(),
        "node": node,
        "snapshotId": None,
        "masterSnapshotId": node['masterSnapshotId'],
        "collection": collection.replace('.', '').lower(),
        "json": {}
    }
    node_type = node['type'] if 'type' in node and node['type'] else 'json'
    json_path = '%s/%s' % (repopath, node['path'])
    file_path = json_path.replace('//', '/')
    logger.info('Dir: %s', file_path)
    if exists_dir(file_path):
        count = 0
        for filename in glob.glob('%s/*.json' % file_path.replace('//', '/')):
            parts = filename.rsplit('/', 1)
            path = '%s/%s' % (node['path'], parts[-1])
            json_data = convert_to_json(filename, node_type)
            logger.info('type: %s, json:%s', node_type, json_data)
            if json_data:
                db_record = copy.deepcopy(d_record)
                db_record['snapshotId'] = '%s%s' % (node['masterSnapshotId'], str(count))
                db_record['path'] = path.replace('//', '/')
                db_record['json'] = json_data
                data_str = json.dumps(json_data)
                db_record['checksum'] = hashlib.md5(data_str.encode('utf-8')).hexdigest()
                db_records.append(db_record)
                count += 1
    else:
        logger.info('Get requires valid directory for snapshot not present!')
    return db_records


def populate_custom_snapshot_orig(snapshot):
    """ Populates the resources from git."""
    user_secret = None
    dbname = config_value('MONGODB', 'dbname')
    snapshot_source = get_field_value(snapshot, 'source')
    sub_data = get_custom_data(snapshot_source)
    snapshot_nodes = get_field_value(snapshot, 'nodes')
    snapshot_data, valid_snapshotids = validate_snapshot_nodes(snapshot_nodes)
    if valid_snapshotids and sub_data and snapshot_nodes:
        giturl = get_field_value(sub_data, 'gitProvider')
        ssh_file = get_field_value(sub_data, 'sshKeyfile')
        brnch = get_field_value(sub_data, 'branchName')
        username = get_field_value(sub_data, 'username')
        if ssh_file:
            if exists_file('%s/%s' % (os.environ['HOME'], ssh_file)):
                ssh_key_file = '%s/%s' % (os.environ['HOME'], ssh_file)
            elif exists_file('%s/.ssh/%s' % (os.environ['HOME'], ssh_file)):
                ssh_key_file = '%s/.ssh/%s' % (os.environ['HOME'], ssh_file)
            else:
                ssh_key_file = None
        else:
            ssh_key_file = None
        # if username:
        #     user_secret = get_vault_data(username)
        #     logger.info('Secret: %s', user_secret)
        repopath = tempfile.mkdtemp()
        logger.info("Repopath: %s", repopath)
        exists, empty = valid_clone_dir(repopath)
        if exists and empty:
            try:
                if ssh_key_file and exists_file(ssh_key_file):
                    # restore, olddir, newdir, ssh_file = make_ssh_dir_before_clone(ssh_key_file)
                    git_ssh_cmd = 'ssh -i %s' % ssh_key_file
                    with Git().custom_environment(GIT_SSH_COMMAND=git_ssh_cmd):
                        repo = Repo.clone_from(giturl, repopath, branch=brnch)
                    # restore_ssh_dir_after_clone(restore, olddir, newdir)
                else:
                    # if username and user_secret:
                    #    giturl = giturl.replace('https://', 'https://%s:%s@' %(username, user_secret))
                    # elif username:
                    #    giturl = giturl.replace('https://', 'https://%s@' % username)
                    repo = Repo.clone_from(giturl, repopath, branch=brnch)
            except Exception as ex:
                logger.info('Unable to clone the repo: %s', ex)
                repo = None
            if repo:
                for node in snapshot_nodes:
                    logger.debug(node)
                    data = get_node(repopath, node, snapshot_source, brnch)
                    if data:
                        insert_one_document(data, data['collection'], dbname)
                        snapshot_data[node['snapshotId']] = True
                if os.path.exists(repopath):
                    logger.info('Repo path: %s', repopath)
                    shutil.rmtree(repopath)
        # elif exists and not empty:
        #     try:
        #         Repo(repopath)
        #         logger.info("A repository exists in this directory: %s", repopath)
        #     except:
        #         logger.info("A non-empty directory, clean it and run: %s", repopath)
    return snapshot_data



def valid_clone_dir(dirname):
    if exists_dir(dirname):
        exists = True
        if not os.listdir(dirname):
            empty = True
        else:
            empty = False
    else:
        exists = mkdir_path(dirname)
        if exists and not os.listdir(dirname):
            empty = True
        else:
            empty = False
    return exists, empty


def restore_ssh_dir_after_clone(restore, olddir, newdir):
    if restore:
        if exists_dir(olddir):
            shutil.rmtree(newdir, ignore_errors=True)
        if exists_dir(newdir):
            os.rename(newdir, olddir)


def make_ssh_dir_before_clone(ssh_key_file):
    restore = False
    newdir = None
    olddir = None
    ssh_file = None
    if ssh_key_file and exists_file(ssh_key_file):
        restore = True
        tempdir = tempfile.mkdtemp()
        # print(tempdir)
        ssh_parts = ssh_key_file.rsplit('/', 1)
        new_ssh_key_file = '%s/%s' % (tempdir, ssh_parts[-1])
        # print(new_ssh_key_file)
        shutil.copy(ssh_key_file, new_ssh_key_file)
        olddir = '%s/.ssh' % os.environ['HOME']
        # print(olddir)
        if exists_dir(olddir):
            newdir = '%s_old' % olddir
            # print(newdir)
            if exists_dir(newdir):
                shutil.rmtree(newdir, ignore_errors=True)
            os.rename(olddir, newdir)
        os.mkdir(olddir)
        ssh_file = '%s/id_rsa' % olddir
        shutil.copy(new_ssh_key_file, ssh_file)
        remove_file(new_ssh_key_file)
        cfg = '%s/config' % olddir
        with open(cfg, 'w') as f:
            f.write('Host *\n')
            f.write('    StrictHostKeyChecking no\n')
    return restore, olddir, newdir, ssh_file


def create_ssh_config(ssh_dir, ssh_key_file, ssh_user):
    ssh_config = '%s/config' % ssh_dir
    if exists_file(ssh_config):
        logger.error("Git config: %s already exists, cannot modify it!")
        return None
    with open(ssh_config, 'w') as f:
        f.write('Host *\n')
        # f.write('Host %s\n' % ssh_host)
        # f.write('   HostName %s\n' % ssh_host)
        f.write('   User %s\n' % ssh_user)
        f.write('   IdentityFile %s\n\n' % ssh_key_file)
        # f.write('Host *\n')
        f.write('   IdentitiesOnly yes\n')
        f.write('   ServerAliveInterval 100\n')
    return ssh_config


def get_git_pwd(key='GIT_PWD'):
    """ Return the git password for https connection"""
    git_pwd = get_from_currentdata('GIT_PWD')
    if not git_pwd:
        git_pwd = os.getenv(key, None)
    return git_pwd


def run_subprocess_cmd(cmd, ignoreerror=False, maskoutput=False, outputmask="Error output is masked"):
    """ Run a sub-process command"""
    result = ''
    errresult = None
    if cmd:
        if isinstance(cmd, list):
            cmd = ' '.join(cmd)
        myprocess = Popen(cmd, shell=True, stdout=PIPE,
                                     stderr=PIPE,
                                     stdin=PIPE)
        out, err = myprocess.communicate()
        result = out.rstrip()
        errresult = err.rstrip() if err else None
        if isinstance(result, bytes):
            result = result.decode()
        if errresult and isinstance(errresult, bytes):
            errresult = errresult.decode()
        if not ignoreerror and errresult:
            if maskoutput:
                logger.info("OUTPUT: %s, ERROR: %s", outputmask, outputmask)
            else:
                logger.info("CMD: '%s', OUTPUT: %s, ERROR: %s", cmd, result, errresult)
    return errresult, result


def git_clone_dir(connector):
    clonedir = None
    repopath = tempfile.mkdtemp()
    subdir = False
    if connector and isinstance(connector, dict):
        giturl = get_field_value(connector, 'gitProvider')
        if not giturl:
            logger.error("Git connector does not have valid git provider URL")
            return repopath, clonedir
        brnch = get_field_value_with_default(connector, 'branchName', 'master')
        isprivate = get_field_value(connector, 'private')
        isprivate = True if isprivate is None or not isinstance(isprivate, bool) else isprivate
        logger.info("Repopath: %s", repopath)
        http_match = re.match(r'^http(s)?://', giturl, re.I)
        if http_match:
            logger.info("Http (private:%s) giturl: %s, Repopath: %s", "YES" if isprivate else "NO",
                        giturl, repopath)
            username = get_field_value(connector, 'httpsUser')
            if username:
                pwd = get_field_value(connector, 'httpsPassword')
                schema = giturl[:http_match.span()[-1]]
                other_part = giturl[http_match.span()[-1]:]
                pwd = pwd if pwd else get_git_pwd()
                if pwd:
                    git_cmd = 'git clone %s%s:%s@%s %s' % (schema, urllib.parse.quote_plus(username),
                                                        urllib.parse.quote_plus(pwd), other_part, repopath)
                else:
                    git_cmd = 'git clone %s%s@%s %s' % (schema, urllib.parse.quote_plus(username),
                                                     other_part, repopath)
            else:
                git_cmd = 'git clone %s %s' % (giturl, repopath)
        else:
            logger.info("SSH (private:%s) giturl: %s, Repopath: %s", "YES" if isprivate else "NO",
                        giturl, repopath)
            if isprivate:
                ssh_key_file = get_field_value(connector, 'sshKeyfile')
                if not exists_file(ssh_key_file):
                    logger.error("Git connector points to a non-existent ssh keyfile!")
                    return repopath, clonedir
                ssh_host = get_field_value(connector, 'sshHost')
                ssh_user = get_field_value_with_default(connector, 'sshUser', 'git')
                if not ssh_host:
                    logger.error("SSH host not set, could be like github.com, gitlab.com, 192.168.1.45 etc")
                    return repopath, clonedir
                ssh_dir = '%s/.ssh' % repopath
                if exists_dir(ssh_dir):
                    logger.error("Git ssh dir: %s already exists, cannot recreate it!", ssh_dir)
                    return repopath, clonedir
                os.mkdir('%s/.ssh' % repopath, 0o700)
                ssh_cfg = create_ssh_config(ssh_dir, ssh_key_file, ssh_user)
                if not ssh_cfg:
                    logger.error("Creation of Git ssh config in dir: %s failed!", ssh_dir)
                    return repopath, clonedir
                git_ssh_cmd = 'ssh -o "StrictHostKeyChecking=no" -F %s' % ssh_cfg
                git_cmd = 'git clone %s %s/tmpclone' % (giturl, repopath)
                subdir = True
            else:
                git_ssh_cmd = 'ssh -o "StrictHostKeyChecking=no"'
                git_cmd = 'git clone %s %s' % (giturl, repopath)
            os.environ['GIT_SSH_COMMAND'] = git_ssh_cmd
            logger.info("GIT_SSH_COMMAND=%s", git_ssh_cmd)
        git_cmd = '%s --branch %s' % (git_cmd, brnch)
        logger.info("os.system(%s)", git_cmd)
        if git_cmd:
            run_subprocess_cmd(git_cmd)
            checkdir = '%s/tmpclone' % repopath if subdir else repopath
            clonedir = checkdir if exists_dir('%s/.git' % checkdir) else None
        if 'GIT_SSH_COMMAND' in os.environ:
            os.environ.pop('GIT_SSH_COMMAND')
    return repopath, clonedir


def _local_file_directory(connector):
    final_path = None
    repopath = None
    if connector and isinstance(connector, dict):
        folder_path = get_field_value(connector, 'folderPath')
        if not folder_path:
            logger.error("Folder path missing.")
            return repopath, final_path
        logger.info("Folder path: %s", folder_path)
        if exists_dir(folder_path):
            final_path = folder_path
    return repopath, final_path


def _get_repo_path(connector):
    if connector and isinstance(connector, dict):
        file_type = get_field_value(connector, "fileType")
        git_provider = get_field_value(connector, "gitProvider")
        folder_path = get_field_value(connector, "folderPath")
        if file_type == "git" and git_provider:
            return git_clone_dir(connector)

        if file_type == "filesystem" and folder_path:
            return _local_file_directory(connector)
    else:
        return None, None


def populate_custom_snapshot(snapshot):
    """ Populates the resources from git."""
    dbname = config_value('MONGODB', 'dbname')
    snapshot_source = get_field_value(snapshot, 'source')
    sub_data = get_custom_data(snapshot_source)
    snapshot_nodes = get_field_value(snapshot, 'nodes')
    snapshot_data, valid_snapshotids = validate_snapshot_nodes(snapshot_nodes)
    if valid_snapshotids and sub_data and snapshot_nodes:
        baserepo, repopath = _get_repo_path(sub_data)
        if repopath:
            brnch = get_field_value_with_default(sub_data, 'branchName', 'master')
            for node in snapshot_nodes:
                # logger.debug(node)
                # data = get_node(repopath, node, snapshot_source, brnch)
                # if data:
                #     insert_one_document(data, data['collection'], dbname)
                #     snapshot_data[node['snapshotId']] = True
                validate = node['validate'] if 'validate' in node else True
                if 'snapshotId' in node:
                    logger.debug(node)
                    data = get_node(repopath, node, snapshot_source, brnch)
                    if data:
                        if validate:
                            insert_one_document(data, data['collection'], dbname)
                            if 'masterSnapshotId' in node:
                                snapshot_data[node['snapshotId']] = node['masterSnapshotId']
                            else:
                                snapshot_data[node['snapshotId']] = True
                        else:
                            snapshot_data[node['snapshotId']] = False
                        node['status'] = 'active'
                    else:
                        node['status'] = 'inactive'
                    logger.debug('Type: %s', type(data))
                elif 'masterSnapshotId' in node:
                    alldata = get_all_nodes(repopath, node, snapshot_source, brnch)
                    if alldata:
                        snapshot_data[node['masterSnapshotId']] = []
                        for data in alldata:
                            snapshot_data[node['masterSnapshotId']].append(
                                {
                                    'snapshotId': data['snapshotId'],
                                    'path': data['path'],
                                    'validate': True
                                })
                    logger.debug('Type: %s', type(alldata))
        if baserepo and os.path.exists(baserepo):
            logger.info('Repo path: %s', baserepo)
            shutil.rmtree(baserepo)
    return snapshot_data


def main():
    connectors = [
        {
            "fileType": "structure",
            "companyName": "prancer-test",
            "gitProvider": "https://github.com/ajeybk/mytest.git",
            "branchName": "master",
            "username": None,
            "password": None,
            "sshKeyfile": None,
            "private": True,
            "sshHost": "github.com",
            "sshUser": "git"
        },
        {
            "fileType": "structure",
            "companyName": "prancer-test",
            "gitProvider": "https://github.com/ajeybk/mytest.git",
            "branchName": "master",
            "username": "kbajey@gmail.com",
            "password": None,
            "sshKeyfile": None,
            "private": True,
            "sshHost": "github.com",
            "sshUser": "git"
        },
        {
            "fileType": "structure",
            "companyName": "prancer-test",
            "gitProvider": "https://github.com/ajeybk/mytest.git",
            "branchName": "master",
            "username": "ajeybk",
            "password": None,
            "sshKeyfile": None,
            "private": True,
            "sshHost": "github.com",
            "sshUser": "git"
        },
        {
            "fileType": "structure",
            "companyName": "prancer-test",
            "gitProvider": "git@github.com:ajeybk/mytest.git",
            "branchName": "master",
            "username": "ajeybk",
            "sshKeyfile": "/home/ajey/ssh_working/id_rsa_bitbucket",
            "private": True,
            "sshHost": "github.com",
            "sshUser": "git"
        },
        {
            "fileType": "structure",
            "companyName": "prancer-test",
            "gitProvider": "https://github.com/prancer-io/cloud-validation-framework.git",
            "branchName": "master",
            "username": "kbajey@gmail.com",
            "password": None,
            "sshKeyfile": None,
            "private": False,
            "sshHost": "github.com",
            "sshUser": "git"
        }
    ]
    for conn in connectors:
        logger.info('#' * 50)
        repodir, clonedir = git_clone_dir(conn)
        logger.info("Delete: %s, clonedir: %s", repodir, clonedir)



if __name__ == "__main__":
    main()