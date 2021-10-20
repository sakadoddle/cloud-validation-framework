"""
   This is driver function to initiate the cloud validation framework for command line.
   The following are the steps to invoke the validator_main() function:
   1) Clone the repository
        git clone https://github.com/prancer-io/cloud-validation-framework.git <cloned-directory>
        cd <cloned-directory>
        export BASEDIR=`pwd`
   2) Install virtualenv(if not present) and create a virtualenv
        virtualenv --python=python3 cloudenv
        source cloudenv/bin/activate
   3) Install mongo server and start the mongo database services. All the data fetched from the
      different clouds is stored in different/same collections as configured in config.ini
   4) Set environment variables
        export PYTHONPATH=$BASEDIR/src
        export FRAMEWORKDIR=$BASEDIR
   5) Edit $BASEDIR/realm/config.ini for detailed logging to be info
        level = INFO
   6) Run the cloud validation tests for different containers (default LOGLEVEL=ERROR)
        python utilities/validator.py container1
        LOGLEVEL=DEBUG python utilities/validator.py   -- Set LOGLEVEL for this run
        LOGLEVEL=INFO python utilities/validator.py   -- Set to INFO for this run.

   The following steps when the prancer-basic is installed, instead of cloning the repository.
   1) Install virtualenv(if not present) and create a virtualenv
        export BASEDIR=`pwd`
        virtualenv --python=python3 cloudenv
        source cloudenv/bin/activate
   2) Install mongo server and start the mongo database services. All the data fetched from the
      different clouds is stored in different/same collections as configured in config.ini
   3) Install prancer-basic using pip
         pip install prancer-basic
   4) Download the realm folder from the https://github.com/prancer-io/cloud-validation-framework/tree/master/realm
      and edit the files to populate the tests and structure files.
   5) Set environment variables
        export PYTHONPATH=$BASEDIR/src
        export FRAMEWORKDIR=$BASEDIR
   6) Edit $BASEDIR/realm/config.ini for detailed logging to be info
        level = INFO
   7) Run the cloud validation tests for different containers(default LOGLEVEL=ERROR)
        LOGLEVEL=DEBUG validator container1
        LOGLEVEL=INFO validator container1

   The command line logs in the file under $FRAMEWORKDIR/log/<logfile>.log, only the steps which are
   marked critical are logged. All error conditions are also logged. Some of the error conditions logged:
      1) Unable to initiate mongo connection, log error and exit
      2) Unable to find tests, snapshots or structure data in database or in filesystem  and continue
      3) Unable to connect using connector for the snapshot and continue.
   For more logging level=INFO or level=DEBUG in the config.ini gives broader logging details of the process.

   FRAMEWORKDIR is required to know config.ini location, if not set will consider the current directory
   as the FRAMEWORKDIR and $FRAMEWORKDIR/realm/config.ini

"""

import argparse
import threading
import sys
import datetime
import atexit
import json
import os
import signal
from inspect import currentframe, getframeinfo
from processor.helper.config.config_utils import COMPLIANCE, CRAWL, CRAWL_AND_COMPLIANCE, framework_dir, config_value, framework_config, \
    CFGFILE, get_config_data, SNAPSHOT, DBVALUES, TESTS, DBTESTS, NONE, REMOTE, CUSTOMER, \
    SINGLETEST, EXCLUSION, container_exists
from processor.helper.file.file_utils import exists_file, exists_dir, mkdir_path
from processor import __version__
import traceback
from jinja2 import Environment, FileSystemLoader

from processor.reporting.json_output import create_output_entry, dump_output_results
current_progress = None

def handler(signum, cf):
    message = "%d Signal handler called with signal" % signum
    print('Signal handler called with signal', signum)
    filename = getframeinfo(cf).filename
    line = cf.f_lineno
    now = datetime.datetime.now()
    fmtstr = '%s,%s(%s: %3d) %s' % (now.strftime('%Y-%m-%d %H:%M:%S'), str(now.microsecond)[:3],
                                    os.path.basename(filename).replace('.py', ''), line, message)
    print(fmtstr)
    from processor.helper.config.rundata_utils import get_from_currentdata
    if current_progress == 'CRAWLERSTART':
        from processor.crawler.master_snapshot import update_crawler_run_status
        update_crawler_run_status('Cancelled')
    elif current_progress == 'COMPLIANCESTART':
        dump_output_results([], get_from_currentdata('container'), test_file="", snapshot="", filesystem=False, status="Cancelled")
    else:
        print("Killed after completion, not updating to cancelled")
        dump_output_results([], get_from_currentdata('container'), test_file="", snapshot="", filesystem=False, status="Cancelled")

    print("Exiting....received SIGTERM!....")
    sys.exit(2)

current_progress = None

def handler(signum, cf):
    message = "%d Signal handler called with signal" % signum
    print('Signal handler called with signal', signum)
    filename = getframeinfo(cf).filename
    line = cf.f_lineno
    now = datetime.datetime.now()
    fmtstr = '%s,%s(%s: %3d) %s' % (now.strftime('%Y-%m-%d %H:%M:%S'), str(now.microsecond)[:3],
                                    os.path.basename(filename).replace('.py', ''), line, message)
    print(fmtstr)
    from processor.helper.config.rundata_utils import get_from_currentdata
    fs = get_from_currentdata('jsonsource')
    if fs:
        if current_progress == 'CRAWLERSTART':
            from processor.crawler.master_snapshot import update_crawler_run_status
            update_crawler_run_status('Cancelled')
        elif current_progress == 'COMPLIANCESTART':
            dump_output_results([], get_from_currentdata('container'), test_file="", snapshot="", filesystem=False, status="Cancelled")
        else:
            dump_output_results([], get_from_currentdata('container'), test_file="", snapshot="", filesystem=False, status="Completed")
            print("Killed after completion, not updating to cancelled")

    print("Exiting....received SIGTERM!....")
    sys.exit(2)


def set_customer(cust=None):
    wkEnv = os.getenv('PRANCER_WK_ENV', None)
    customer = cust if cust else os.getenv('CUSTOMER', None)
    if wkEnv and wkEnv.upper() in ['STAGING', 'PRODUCTION']:
        config_path = 'prod' if wkEnv.upper() == 'PRODUCTION' else 'staging'
        if customer:
            os.environ[str(threading.currentThread().ident) + "_SPACE_ID"] = config_path + "/" + customer
        else:
            os.environ[str(threading.currentThread().ident) + "_SPACE_ID"] = "staging/default"
        return True
    elif customer:
        os.environ[str(threading.currentThread().ident) + "_SPACE_ID"] = "staging/" + customer
        return True
    return  False



def console_log(message, cf):
    """Logger like statements only used till logger configuration is read and initialized."""
    filename = getframeinfo(cf).filename
    line = cf.f_lineno
    now = datetime.datetime.now()
    fmtstr = '%s,%s(%s: %3d) %s' % (now.strftime('%Y-%m-%d %H:%M:%S'), str(now.microsecond)[:3],
                                    os.path.basename(filename).replace('.py', ''), line, message)
    print(fmtstr)


def valid_config_ini(config_ini):
    """ Valid config ini path and load the file and check """
    error = None
    if exists_file(config_ini):
        config_data = get_config_data(config_ini)
        if config_data:
            # TODO: can also check for necessary sections and fields.
            pass
        else:
            error = "Configuration(%s) INI file is invalid, correct it and try again!" % config_ini
    else:
        error = "Configuration(%s) INI file does not exist!" % config_ini
    return error


def search_config_ini():
    """Need the config.ini file to read initial configuration data"""
    error = False
    config_ini = None
    fwdir = os.getenv('FRAMEWORKDIR', None)
    if fwdir:
        if exists_dir(fwdir):
            config_ini = '%s/%s' % (fwdir, CFGFILE)
            error_msg = valid_config_ini(config_ini)
            if error_msg:
                console_log("FRAMEWORKDIR: %s, env variable directory exists, checking...." % fwdir, currentframe())
                console_log(error_msg, currentframe())
                error = True
        else:
            console_log("FRAMEWORKDIR: %s, env variable set to non-existent directory, exiting....." % fwdir, currentframe())
            error = True
    else:
        config_ini = '%s/%s' % (os.getcwd(), CFGFILE)
        error_msg = valid_config_ini(config_ini)
        if error_msg:
            console_log("FRAMEWORDIR environment variable NOT SET, searching in current directory.", currentframe())
            console_log(error_msg, currentframe())
            error = True
    return error, config_ini


def validator_main(arg_vals=None, delete_rundata=True):
    """
    Main driver utility for running validator tests
    The arg_vals, if passed should be array of string. A set of examples are:
      1) arg_vals = ['container1'] - Use container1 to process test files from filesystem
      2) args_vals = ['container1', '--db'] - Use container1 to process test documents from database.
    When arg_vals is None, the argparse library parses from sys.argv array list.
    The successful argument parsing initializes the system for the run.
    On exit will run cleanup. The return values of this main entry function are as:
       0 - Success, tests executed.
       1 - Failure, Tests execution error.
       2 - Exception, missing config.ini, Mongo connection failure or http connection exception,
           the tests execution could not be started or completed.
    """
    global  current_progress
    cmd_parser = argparse.ArgumentParser("prancer", formatter_class=argparse.RawDescriptionHelpFormatter,
                                         epilog='''\
Example: prancer collection1
Runs the prancer framework based on the configuration files available in collection1 folder
                                         ''')
    cmd_parser.add_argument('-v','--version', action='version', version=("Prancer %s" % __version__) , help='Show prancer version')
    cmd_parser.add_argument('container', metavar='collection', action='store', nargs='?', default='',
                            help='The name of the folder which contains the collection of files related to one scenario')
    cmd_parser.add_argument('--db', action='store', default=None, choices=['NONE', 'SNAPSHOT', 'FULL', 'REMOTE'],
                            help='''NONE - Database will not be used, all the files reside on file system,
                            SNAPSHOT - Resource snapshots will be stored in db, everything else will be on file system,
                            FULL - tests, configurations, outputs and snapshots will be stored in the database
                            REMOTE - tests, configurations, outputs and snapshots will be downloaded from the API server and run as NONE mode.''')
    cmd_parser.add_argument('--crawler', action='store_true', default=False,
                            help='Crawls and generates snapshot files only')
    cmd_parser.add_argument('--test', action='store', default=None, help='Run a single test in NODB mode')
    cmd_parser.add_argument('--compliance', action='store_true', default=False, help='Run only compliance on snapshot file')
    cmd_parser.add_argument('--customer', action='store', default=None, help='customer name for config')
    cmd_parser.add_argument('--connector', action='store', default=None, help='specify the name of the connector which you want to run from the collection')
    cmd_parser.add_argument('--branch', action='store', default=None, help='specify the name of the branch to populate snapshots, for the filesystem connector')
    cmd_parser.add_argument('--file', action='store', default=None, help='single file run')
    cmd_parser.add_argument('--iac', action='store', default=None, help='iac types')
    cmd_parser.add_argument('--file_content', action='store', default=None, help='file content run')
    cmd_parser.add_argument('--mastertestid', action='store', default="", help='test Ids to run')
    cmd_parser.add_argument('--mastersnapshotid', action='store', default="", help='mastersnapshot Ids to run')
    cmd_parser.add_argument('--snapshotid', action='store', default="", help='snapshot Ids to run')
    cmd_parser.add_argument('--server', action='store', default='LOCAL', choices=['DEV', 'QA', 'PROD', 'LOCAL'],
                            help='''DEV - API server is in a dev environment,
                            QA - API server is in a qa environment,
                            PROD - API server is in a prod environment
                            LOCAL - API server is in a local environment.''')
    cmd_parser.add_argument('--apitoken', action='store', default=None, help='API token to access the server.')
    cmd_parser.add_argument('--company', action='store', default=None, help='company of the API server')

    args = cmd_parser.parse_args(arg_vals)

    retval = 2
    set_customer()
    cfg_error, config_ini = search_config_ini()
    if cfg_error:
        return retval

    if args.customer:
        set_customer(args.customer)

    args.remote = False
    args.opath = None
    if args.db and args.db.upper() == REMOTE:
        from processor.helper.utils.compliance_utils import create_container_compliance, get_api_server, \
            get_collection_api
        from processor.helper.httpapi.http_utils import http_get_request, http_post_request
        remoteValid = False
        if not args.apitoken:
            args.apitoken = os.environ['APITOKEN'] if 'APITOKEN' in os.environ else None
        if args.apitoken:
            apiserver = get_api_server(args.server, args.company)
            if apiserver:
                collectionUri = get_collection_api(apiserver, args.container)
                hdrs = {
                    "Authorization": "Bearer %s" % args.apitoken,
                    "Content-Type": "application/json"
                }
                status, data = http_get_request(collectionUri, headers=hdrs)
                if status and isinstance(status, int) and status == 200:
                    if 'data' in data:
                        collectionData = data['data']
                        opath = create_container_compliance(args.container, collectionData)
                        if opath:
                            remoteValid = True
                            args.remote = True
                            args.opath = opath
                            args.db = NONE
        if not remoteValid:
            msg = "Check the remote configuration, exiting!....."
            console_log(msg, currentframe())
            return retval
    # return retval

    if args.db:
        if args.db.upper() in DBVALUES:
            args.db = DBVALUES.index(args.db.upper())
        else:
            args.db = DBVALUES.index(SNAPSHOT)
    else:
        nodb = config_value(TESTS, DBTESTS)
        if nodb and nodb.upper() in DBVALUES:
            args.db = DBVALUES.index(nodb.upper())
        else:
            args.db = DBVALUES.index(SNAPSHOT)

    if args.test:
        args.db = DBVALUES.index(NONE)

    # Check if we want to run in NO DATABASE MODE
    if args.db:
        # returns the db connection handle and status, handle is ignored.
        from processor.database.database import init_db, TIMEOUT
        _, db_init_res = init_db()
        if not db_init_res:
            msg = "Mongo DB connection timed out after %d ms, check the mongo server, exiting!....." % TIMEOUT
            console_log(msg, currentframe())
            return retval

    # Check the log directory and also check if it is writeable.
    from processor.logging.log_handler import init_logger, get_logdir
    fw_cfg = get_config_data(framework_config())
    log_writeable, logdir = get_logdir(fw_cfg, framework_dir())
    if not log_writeable:
        console_log('Logging directory(%s) is not writeable, exiting....' % logdir, currentframe())
        return retval

    # Alls well from this point, check container exists in the directory configured
    retval = 0
    logger = init_logger(DBVALUES.index(REMOTE) if args.remote else args.db, framework_config())
    # logger = add_file_logging(config_ini)
    logger.info("START: Argument parsing and Run Initialization. Version %s", __version__)


    from processor.connector.snapshot import populate_container_snapshots, populate_container_exclusions
    from processor.connector.validation import run_container_validation_tests, run_filecontent_validation
    from processor.crawler.master_snapshot import generate_container_mastersnapshots
    try:
        from processor_enterprise.notifications.notification import check_send_notification
    except:
        check_send_notification = lambda container, db: None

    logger.info("Command: '%s %s'", sys.executable.rsplit('/', 1)[-1], ' '.join(sys.argv))
    try:
        from processor.helper.config.rundata_utils import init_currentdata, \
            delete_currentdata, put_in_currentdata
        # Delete the rundata at the end of the script as per caller, default is True.
        if delete_rundata:
            atexit.register(delete_currentdata)

        signal.signal(signal.SIGTERM, handler)
        init_currentdata()

        logger.info("Using Framework dir: %s", framework_dir())
        logger.info("Args: %s", args)
        logger.info("Pid: %s", os.getpid())
        logger.debug("Running tests from %s.", DBVALUES[args.db])
        fs = True if args.db > DBVALUES.index(SNAPSHOT) else False
        put_in_currentdata('jsonsource', fs)
        put_in_currentdata(DBTESTS, args.db)
        put_in_currentdata( 'container', args.container)
        put_in_currentdata("CLEANING_REPOS", [])
        if args.mastersnapshotid:
            put_in_currentdata("INCLUDESNAPSHOTS", True)
            put_in_currentdata("SNAPHSHOTIDS", args.mastersnapshotid.split(','))
        else:
            put_in_currentdata("INCLUDESNAPSHOTS", False)
            put_in_currentdata("SNAPHSHOTIDS", [])
        if args.mastertestid:
            put_in_currentdata("INCLUDETESTS", True)
            put_in_currentdata("TESTIDS", args.mastertestid.split(','))
        else:
            put_in_currentdata("INCLUDETESTS", False)
            put_in_currentdata("TESTIDS", [])
        if args.snapshotid:
            put_in_currentdata("ONLYSNAPSHOTS", True)
            put_in_currentdata("ONLYSNAPSHOTIDS", args.snapshotid.split(','))
        else:
            put_in_currentdata("ONLYSNAPSHOTS", False)
            put_in_currentdata("ONLYSNAPSHOTIDS", [])
        
        # if args.db == DBVALUES.index(FULL):
        #     from processor.logging.log_handler import get_dblogger
        #     log_name = get_dblogger()
        #     if log_name:
        #         pid = open('/tmp/pid_%s' % os.getpid(), 'w')
        #         pid.write(log_name)
        #         pid.close()
        if args.customer:
            put_in_currentdata(CUSTOMER, args.customer)
        if args.test:
            put_in_currentdata(SINGLETEST, args.test)
        else:
            put_in_currentdata(SINGLETEST, False)
        if args.connector:
            put_in_currentdata("connector", args.connector)
        if args.branch:
            put_in_currentdata("branch", args.branch)
        if not args.db and not args.file:
            retval = 0 if container_exists(args.container) else 2
            if retval:
                logger.critical("Container(%s) is not present in Framework dir: %s",
                                args.container, framework_dir(), extra={"type" : "critical"})
                # TODO: Log the path the framework looked for.
                return retval

        if args.file and args.iac:
            container = generate_file_container(args.file, args.iac)
            # container = generate_file_container("mydata/deploy.yaml", 'cloudformation')
            args.container = container
            args.db  = DBVALUES.index(NONE)

        put_in_currentdata(EXCLUSION, populate_container_exclusions(args.container, fs))

        if args.file_content:
            current_progress = 'COMPLIANCESTART'
            create_output_entry(args.container, test_file="-", filesystem=True if args.db == 0 else False)
            snapshot_status = populate_container_snapshots(args.container, fs)
            status = run_filecontent_validation(args.container, snapshot_status, args.testIds.split(',') if args.testIds else [])
            retval = 0 if status else 1
            if fs:
                dump_output_results([], args.container, test_file="", snapshot="", filesystem=fs, status="Completed")
            current_progress = 'COMPLIANCECOMPLETE'
            return retval

        crawl_and_run = False
        if not args.compliance and not args.crawler:
            crawl_and_run = True
            put_in_currentdata("run_type", CRAWL_AND_COMPLIANCE)

        if args.crawler or crawl_and_run:
            # Generate snapshot files from here.
            current_progress = 'CRAWLERSTART'
            if not crawl_and_run:
                put_in_currentdata("run_type", CRAWL)
            generate_container_mastersnapshots(args.container, fs)
            current_progress = 'CRAWLERCOMPLETE'
        
        if args.compliance or crawl_and_run:
            current_progress = 'COMPLIANCESTART'
            if not crawl_and_run:
                put_in_currentdata("run_type", COMPLIANCE)
            create_output_entry(args.container, test_file="-", filesystem=True if args.db ==  0 else False)
            # Normal flow
            snapshot_status = populate_container_snapshots(args.container, fs)
            logger.debug(json.dumps(snapshot_status, indent=2))
            if snapshot_status:
                status = run_container_validation_tests(args.container, fs, snapshot_status)
                retval = 0 if status else 1
            else:
                retval = 1
            check_send_notification(args.container, args.db)

            if fs:
                dump_output_results([], args.container, test_file="", snapshot="", filesystem=fs, status="Completed")
            current_progress = 'COMPLIANCECOMPLETE'
    except (Exception, KeyboardInterrupt) as ex:
        if current_progress == 'CRAWLERSTART':
            from processor.crawler.master_snapshot import update_crawler_run_status
            update_crawler_run_status('Completed')
        else:
            dump_output_results([], args.container, test_file="", snapshot="", filesystem=False, status="Completed")

        logger.error("Execution exception: %s", ex)
        print(traceback.format_exc())
        retval = 2

    if args.remote:
        from processor.helper.utils.compliance_utils import upload_compliance_results
        upload_compliance_results(args.container, args.opath, args.server, args.company, args.apitoken)
    return retval


def generate_file_container(filename, iacType):
    iacs = {
        'cloudformation': {'abbrev': 'CFR', 'dir': 'aws'},
        'arm': {'abbrev': 'ARM', 'dir': 'azure'},
        'kubernetesObjectFiles': {'abbrev': 'K8S', 'dir': 'kubernetes'},
        'helmChart': {'abbrev': 'K8S', 'dir': 'kubernetes'},
        'deploymentmanager': {'abbrev': 'GDF', 'dir': 'google'}
    }

    frameworkdir = os.environ['FRAMEWORKDIR']
    containerFolder =  config_value('TESTS', 'containerFolder')
    structureFolder = config_value('AZURE', 'azureStructureFolder')
    container = 'singleData%s' % iacType
    containerDir = '%s/%s/%s' % (frameworkdir, containerFolder, container)
    structureDir = '%s/%s' % (frameworkdir, structureFolder)
    dataDir = '%s/data' % containerDir
    mkdir_path(dataDir)
    fsconnector = 'fs_connector'
    git_connector = 'git_connector'
    with open(filename) as f, open('%s/%s' % (dataDir, os.path.basename(filename)), 'w') as w:
        filedata = f.read()
        w.write(filedata)

    mt_data = {
        'iacType': iacType,
        'iacDir': iacs[iacType]['dir'],
        'connector': git_connector,
    }

    ms_data = {
        'user': 'USER_1',
        'abbrev': iacs[iacType]['abbrev'],
        'iacType': iacType,
        'container': container,
        'connector': fsconnector
    }

    tpath = '%s/jinjatemplates' % os.path.dirname(__file__)

    gen_config_file('%s/mastersnapshot.json' % containerDir, tpath, 'mastersnapshot.json', ms_data)

    gen_config_file('%s/mastertest.json' % containerDir, tpath, 'mastertest.json', mt_data)

    gen_config_file('%s/%s.json' % (structureDir, git_connector), tpath, '%s.json' % git_connector, {})

    gen_config_file('%s/%s.json' % (structureDir, fsconnector), tpath,
                    '%s.json' % fsconnector, {'basedir': '%s/%s' % (frameworkdir, containerFolder)})

    return container

def gen_config_file(fname, path, template, data):
    env = Environment(loader=FileSystemLoader(path))
    template = env.get_template(template)
    output_from_parsed_template = template.render(**data)
    # print(output_from_parsed_template)
    with open(fname, 'w') as f:
        f.write(output_from_parsed_template)
    return output_from_parsed_template

