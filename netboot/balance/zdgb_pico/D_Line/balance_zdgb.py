# Embedded file name: balance_zdgb.py
import os
import ConfigParser
import sys
import logging
import time
import thread
import threading
import commands
import subprocess
logging.basicConfig(filename='/tmp/test-zdgb.log', format='%(asctime)s:%(levelname)s:%(message)s', level=logging.DEBUG)
INI = 'zdgb.ini'
BASE_PATH = '/mnt/star'
BASE_PATH1 = '/mnt/55'
BASE_PATH2 = '/mnt/66'
BASE_PATH3 = '/mnt/77'
BASEFILE = 'omahaserver_pico.conf'
USERNAME = 'A0010415'
PASSWORD = 'PU4+stnswpe'
DOMAIN = 'quantacn'
WDSIP1 = '40.31.1.55'
WDSIP2 = '40.31.1.66'
WDSIP3 = '40.31.1.77'

def CalSection(ini):
    try:
        config = ConfigParser.RawConfigParser()
        config.read(ini)
        section = config.sections()
    except ConfigParser.NoSectionError as e:
        logging.info('CalSection Section Error')
        sys.exit(3)
    else:
        return section


def ReadIni(ini, section, option, option1, option2, option3, option4, option5, option6):
    try:
        config = ConfigParser.ConfigParser()
        config.read(ini)
        IP1 = config.get(section, option)
        PORT1 = config.getint(section, option1)
        IP2 = config.get(section, option2)
        PORT2 = config.getint(section, option3)
        IP3 = config.get(section, option4)
        PORT3 = config.getint(section, option5)
        TIME = config.getint(section, option6)
    except ConfigParser.NoSectionError as e:
        logging.info('Section Error')
        sys.exit(4)
    except ConfigParser.DuplicateSectionError as e:
        logging.info('Duplicate Section Error')
        sys.exit(5)
    except ConfigParser.NoOptionError as e:
        logging.info('Option Error')
        sys.exit(6)
    else:
        return (IP1,
         PORT1,
         IP2,
         PORT2,
         IP3,
         PORT3,
         TIME)


def WriteConf(basepath, basefile, content):
    try:
        with open(os.path.join(basepath, basefile), 'w') as f:
            f.write(content)
    except IOError:
        logging.info('Write failed,base path is not correct')
        try:
            with open(os.path.join(basepath, basefile), 'w') as f:
                f.write(content)
        except IOError:
            logging.info('Write failed,base path is not correct.try again')


def ReadConf(basepath, basefile):
    file_object = open(os.path.join(basepath, basefile), 'r')
    try:
        all_the_text = file_object.readlines()
        for line in all_the_text:
            line = line.strip('\n')

    except IOError:
        logging.info('Read failed,base path is not correct.')
    else:
        return line


def RunRsync(*rsync_command):
    """Runs rsync with the given command."""
    rsync = subprocess.Popen(rsync_command, stdout=subprocess.PIPE, shell=True)
    stdout, _ = rsync.communicate()
    if stdout:
        logging.info('rsync output: %s', stdout)
    if rsync.returncode:
        raise UpdaterException('mount failed %d; aborting' % rsync.returncode)


def CheckConf11():
    global BASE_PATH1
    commands.getoutput('umount %s' % BASE_PATH1)
    RunRsync('again:mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
     DOMAIN,
     PASSWORD,
     WDSIP1,
     BASE_PATH1))
    logging.info('mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
     DOMAIN,
     PASSWORD,
     WDSIP1,
     BASE_PATH1))
    time.sleep(5)


def CheckConf12():
    global BASE_PATH2
    commands.getoutput('umount %s' % BASE_PATH2)
    RunRsync('again:mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
     DOMAIN,
     PASSWORD,
     WDSIP2,
     BASE_PATH2))
    logging.info('mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
     DOMAIN,
     PASSWORD,
     WDSIP2,
     BASE_PATH2))
    time.sleep(5)


def CheckConf13():
    global BASE_PATH3
    commands.getoutput('umount %s' % BASE_PATH3)
    RunRsync('again:mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
     DOMAIN,
     PASSWORD,
     WDSIP3,
     BASE_PATH3))
    logging.info('mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
     DOMAIN,
     PASSWORD,
     WDSIP3,
     BASE_PATH3))
    time.sleep(5)


class balance(threading.Thread):

    def __init__(self, model, basefile, ini):
        threading.Thread.__init__(self)
        self.basefile = basefile
        self.ini = ini
        self.thread_stop = False
        self.model = model

    def run(self):
        global BASE_PATH
        circle = 0
        if not os.path.exists(self.ini):
            print 'ini file %s is not exist ,please check!' % self.ini
            logging.info('ini file %s is not exist ,please check!' % self.ini)
            sys.exit(1)
            self.thread_stop = True
        while not self.thread_stop:
            while not os.path.exists(os.path.join(BASE_PATH1, BASEFILE)):
                CheckConf11()

            while not os.path.exists(os.path.join(BASE_PATH2, BASEFILE)):
                CheckConf12()

            while not os.path.exists(os.path.join(BASE_PATH3, BASEFILE)):
                CheckConf13()

            for count in range(len(CalSection(self.ini))):
                result = ReadIni(self.ini, 'Setting%d' % count, 'WDS11_IP', 'WDS11_PORT', 'WDS12_IP', 'WDS12_PORT', 'WDS13_IP', 'WDS13_PORT', 'TIME')
                WriteConf(BASE_PATH1, self.basefile, 'http://%s:%d/update\n' % (result[0], result[1]))
                WriteConf(BASE_PATH2, self.basefile, 'http://%s:%d/update\n' % (result[2], result[3]))
                WriteConf(BASE_PATH3, self.basefile, 'http://%s:%d/update\n' % (result[4], result[5]))
                time.sleep(1)
                logging.info('**************************************************************************************')
                logging.info('%s:WDS 11 server write %s in conf file,delay %ds' % (self.model, ReadConf(BASE_PATH1, self.basefile), result[6]))
                logging.info('%s:WDS 12 server write %s in conf file,delay %ds' % (self.model, ReadConf(BASE_PATH2, self.basefile), result[6]))
                logging.info('%s:WDS 13 server write %s in conf file,delay %ds' % (self.model, ReadConf(BASE_PATH3, self.basefile), result[6]))
                logging.info('**************************************************************************************')
                time.sleep(result[6])
                if os.path.exists(os.path.join(BASE_PATH, 'zdgb.log')):
                    logging.info('logout')
                    self.thread_stop = True
                    break

            circle = circle + 1
            logging.info('current circle:%d' % circle)
            if os.path.exists(os.path.join(BASE_PATH, 'zdgb.log')):
                logging.info('logout')
                self.thread_stop = True

        commands.getoutput('umount %s' % BASE_PATH1)
        time.sleep(1)
        commands.getoutput('umount %s' % BASE_PATH2)
        time.sleep(2)
        commands.getoutput('umount %s' % BASE_PATH3)
        time.sleep(2)
        logging.info('%s terminate')

    def stop(self):
        self.thread_stop = True


if __name__ == '__main__':
    logging.info('start')
    print 'start,keeping monitor........'
    while not os.path.exists(os.path.join(BASE_PATH1, BASEFILE)):
        commands.getoutput('umount %s' % BASE_PATH1)
        RunRsync('mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
         DOMAIN,
         PASSWORD,
         WDSIP1,
         BASE_PATH1))
        logging.info('mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
         DOMAIN,
         PASSWORD,
         WDSIP1,
         BASE_PATH1))
        time.sleep(5)

    while not os.path.exists(os.path.join(BASE_PATH2, BASEFILE)):
        commands.getoutput('umount %s' % BASE_PATH2)
        RunRsync('mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
         DOMAIN,
         PASSWORD,
         WDSIP2,
         BASE_PATH2))
        logging.info('mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
         DOMAIN,
         PASSWORD,
         WDSIP2,
         BASE_PATH2))
        time.sleep(5)

    while not os.path.exists(os.path.join(BASE_PATH3, BASEFILE)):
        commands.getoutput('umount %s' % BASE_PATH3)
        RunRsync('mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
         DOMAIN,
         PASSWORD,
         WDSIP3,
         BASE_PATH3))
        logging.info('mount -t cifs -o username=%s,domain=%s,password=%s //%s/reminst %s' % (USERNAME,
         DOMAIN,
         PASSWORD,
         WDSIP3,
         BASE_PATH3))
        time.sleep(5)
    if os.path.exists(os.path.join(BASE_PATH, 'zdgb.log')):
        os.remove(os.path.join(BASE_PATH, 'zdgb.log'))
        logging.info('del logout')
    thread1 = balance('zdgb', BASEFILE, INI)
    thread1.start()
