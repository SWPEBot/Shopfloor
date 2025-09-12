#!/usr/bin/env python3 

#For A block WDS

import os
import configparser
import sys
import logging
import time
import threading
import subprocess

logging.basicConfig(filename='/tmp/test-zdh.log', format='%(asctime)s:%(levelname)s:%(message)s', level=logging.DEBUG)
INI = 'zdh.ini'
BASE_PATH = '/mnt/star'
BASE_PATH1 = '/mnt/56'
BASE_PATH2 = '/mnt/57'
BASE_PATH3 = '/mnt/58'
BASE_PATH4 = '/mnt/59'
BASEFILE = 'omahaserver_jubilant.conf'
USERNAME = 'A0010415'
PASSWORD = 'PU4+stnswpe'
DOMAIN = 'quantacn'
WDSIP1 = '40.30.1.56'
WDSIP2 = '40.30.1.57'
WDSIP3 = '40.30.1.58'
WDSIP4 = '40.30.1.59'

def CalSection(ini):
    try:
        config = configparser.RawConfigParser()
        config.read(ini)
        section = config.sections()
    except configparser.NoSectionError:
        logging.info('CalSection Section Error')
        sys.exit(3)
    else:
        return section

def ReadIni(ini, section, *options):
    try:
        config = configparser.ConfigParser()
        config.read(ini)
        values = [config.get(section, option) if 'IP' in option else config.getint(section, option) for option in options]
    except (configparser.NoSectionError, configparser.DuplicateSectionError, configparser.NoOptionError) as e:
        logging.info('Config Error: %s', str(e))
        sys.exit(4)
    else:
        return tuple(values)

def WriteConf(basepath, basefile, content):
    try:
        with open(os.path.join(basepath, basefile), 'w') as f:
            f.write(content)
    except IOError:
        logging.info('Write failed, base path is not correct')

def ReadConf(basepath, basefile):
    try:
        with open(os.path.join(basepath, basefile), 'r') as file_object:
            return file_object.read().strip()
    except IOError:
        logging.info('Read failed, base path is not correct.')
        return ''

def RunRsync(rsync_command):
    rsync = subprocess.Popen(rsync_command, stdout=subprocess.PIPE, shell=True)
    stdout, _ = rsync.communicate()
    if stdout:
        logging.info('rsync output: %s', stdout.decode())
    if rsync.returncode:
        raise Exception('mount failed %d; aborting' % rsync.returncode)

def CheckConf(base_path, wds_ip):
    subprocess.getoutput(f'umount {base_path}')
    RunRsync(f'mount -t cifs -o username={USERNAME},domain={DOMAIN},password={PASSWORD} //{wds_ip}/reminst {base_path}')
    logging.info(f'mount -t cifs -o username={USERNAME},domain={DOMAIN},password={PASSWORD} //{wds_ip}/reminst {base_path}')
    time.sleep(5)

class Balance(threading.Thread):
    def __init__(self, model, basefile, ini):
        super().__init__()
        self.basefile = basefile
        self.ini = ini
        self.thread_stop = False
        self.model = model

    def run(self):
        global BASE_PATH
        if not os.path.exists(self.ini):
            print(f'ini file {self.ini} is not exist, please check!')
            logging.info(f'ini file {self.ini} is not exist, please check!')
            sys.exit(1)

        while not self.thread_stop:
            for base_path, wds_ip in zip([BASE_PATH1, BASE_PATH2, BASE_PATH3, BASE_PATH4], [WDSIP1, WDSIP2, WDSIP3, WDSIP4]):
                while not os.path.exists(os.path.join(base_path, BASEFILE)):
                    CheckConf(base_path, wds_ip)

            for count in range(len(CalSection(self.ini))):
                result = ReadIni(self.ini, f'Setting{count}', 'WDS11_IP', 'WDS11_PORT', 'WDS12_IP', 'WDS12_PORT', 'WDS13_IP', 'WDS13_PORT', 'WDS14_IP', 'WDS14_PORT', 'TIME')
                for base_path, (ip, port) in zip([BASE_PATH1, BASE_PATH2, BASE_PATH3, BASE_PATH4], zip(result[::2], result[1::2])):
                    WriteConf(base_path, self.basefile, f'http://{ip}:{port}/update\n')
                time.sleep(result[-1])

                logging.info(f'{self.model}: Updated configuration for all WDS servers')
                if os.path.exists(os.path.join(BASE_PATH, 'zdh.log')):

                    self.thread_stop = True
                    break

        for base_path in [BASE_PATH1, BASE_PATH2, BASE_PATH3, BASE_PATH4]:
            subprocess.getoutput(f'umount {base_path}')
        logging.info(f'{self.model} terminate')

    def stop(self):
        self.thread_stop = True

if __name__ == '__main__':
    logging.info('start')
    print('start, keeping monitor...')

    for base_path, wds_ip in zip([BASE_PATH1, BASE_PATH2, BASE_PATH3, BASE_PATH4], [WDSIP1, WDSIP2, WDSIP3, WDSIP4]):
        while not os.path.exists(os.path.join(base_path, BASEFILE)):
            CheckConf(base_path, wds_ip)

    if os.path.exists(os.path.join(BASE_PATH, 'zdh.log')):
        os.remove(os.path.join(BASE_PATH, 'zdh.log'))
        logging.info('Deleted logout file')

    thread1 = Balance('zdh', BASEFILE, INI)
    thread1.start()
