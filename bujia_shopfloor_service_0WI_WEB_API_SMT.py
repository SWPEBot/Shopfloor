#!/usr/bin/python
#
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
# 2018-07-27 first release

"""Landrid shopfloor proxy implementation."""

import binascii
import collections
import csv
import errno
import logging
import optparse
import os
import re
import random
# import mbpn_to_rampn_yavilla as mbpn_to_rampn  # Sam-san, 2022/03
import SimpleXMLRPCServer
# import xmlrpc.server
import requests
import socket
import json  # region, Sam-san, 2022/07
import SocketServer
import time
import telnetlib

# YG: 2016.0510
import os, platform
from pymssql import connect

# for D1/D2 11090 
DEFAULT_SERVER_PORT = 15010
DEFAULT_SERVER_ADDRESS = '0.0.0.0'
DEFAULT_ROOT_DIR = '/opt/sdt'

# for MonitorAgent Stage
Stage = "WEB"  # WEBAPI mode is preferred. If WEBAPI mode fails,  automatically switch to SQL mode.
# NB5/TOPTEST
MSDB_BU = "NB4"
# "A-block","N11-block","B-block","D-block":,"K-block","O11-block","T-block","S-block","R-block"
LINE = "SMT-block"

RUNIN_TEMP_SPEC = 80
DELAY_SEC = 3

Stage_MonitorAgentVer = {
    "WEB": "WEBAPI2.0.0.1",
    "SQL": "VW20160119.01"
}
# set to True to enable MSDB
_MSDB = True
# TODO(bowgotsai): figure out the pattern for serial number.
MLB_SERIAL_NUMBER_RE = r'.*'
SERIAL_NUMBER_RE = r'.*'
BATT_CT_NUMBER_RE = r'.*'
REGCODE_LOG_CSV = 'registration_code_log.csv'
KEY_SERIAL_NUMBER = "serials.serial_number"
KEY_MLB_SERIAL_NUMBER = "serials.mlb_serial_number"
HWID = "hwid"


# YG: http://stackoverflow.com/questions/2953462/pinging-servers-in-python
def ping(host):
    """
    Returns True if host responds to a ping request
    """
    # Ping parameters as function of OS
    ping_str = "n" if platform.system().lower() == "windows" else "c"
    # Ping
    return os.system("ping -" + ping_str + " 1 " + host) == 0


def Telnet_check(host, port):
    try:
        telnetlib.Telnet(host=host, port=port, timeout=2)
        return True
    except:
        return False


RequestType = collections.namedtuple(
    'RequestType', ('request_dir', 'response_dir', 'request_suffix',
                    'require_line', 'msdb_host', 'msdb_user',
                    'msdb_password', 'msdb_database', 'msdb_sp',
                    'msdb_bu', 'msdb_station', 'msdb_step'))


class RequestTypes(object):
    _msdb_host_line = {
        "A-block": ('40.20.1.1', '40.20.1.2', '40.20.1.3', '10.18.5.101', '10.18.5.102'),
        "B-block": ('40.21.1.1', '40.21.1.2', '40.21.1.3', '10.18.5.121', '10.18.5.122',),
        "D-block": ('40.23.1.1', '40.23.1.2', '40.23.1.3', '10.18.5.161', '10.18.5.162'),
        "K-block": ('40.29.1.1', '40.29.1.2', '40.29.1.3', '10.18.5.94', '10.18.5.112'),
        # SQL used.
        # "N11-block":('30.20.1.6','30.20.1.6','30.20.1.4','10.18.5.61','10.18.5.62','30.20.1.7','30.20.1.5'),
        "N11-block": ('30.20.1.7', '30.20.1.6', '30.20.1.8', '10.18.5.61', '10.18.5.62'),
        "O11-block": ('40.25.1.1', '40.25.1.2', '40.25.1.3', '10.18.5.131', '10.18.5.133'),
        "T-block": ('40.61.1.1', '40.61.1.2', '40.61.1.3', '10.18.9.121', '10.18.9.122'),
        "S-block": ('40.62.1.1', '40.62.1.2', '40.62.1.3', '10.18.9.141', '10.18.9.142'),
        "R-block": ('40.63.1.1', '40.63.1.2', '40.63.1.3', '10.18.9.161', '10.18.9.162'),
        "SMT-block": ('10.94.4.96')
    }
    LIGHT = RequestType(
        'CQ_Monitor/Request', 'CQ_Monitor/Response', '', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'RUNIN', 'ALIVE')
    # for LED update
    LIGHT_UPDATE = RequestType(
        'CQ_Monitor/Request', 'CQ_Monitor/Response', '', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'RUNIN', 'TEST')
    # for D1 Station
    FA_START = RequestType(
        'CQ_Monitor/Request', 'CQ_Monitor/Response', '', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'SWDLTest', 'Request')
    # for DT Station
    FA_START_FAT = RequestType(
        'CQ_Monitor/Handshake', 'CQ_Monitor/HandShakeResp', '', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'SWDLTest', 'Handshake')
    # for 25 Station ,plan to cancel
    FA_START_FRT = RequestType(
        'CQ_Monitor/Handshake', 'CQ_Monitor/HandShakeResp', '', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'FRT', 'Request')
    # for RT Staion
    FA_START_RT = RequestType(
        'CQ_Monitor/Handshake', 'CQ_Monitor/HandShakeResp', '', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'RTPASS', 'Request')
    # for Monitor temperature
    FA_START_TEMP = RequestType(
        'CQ_Monitor/Handshake', 'CQ_Monitor/HandShakeResp', '', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'MonitorTemperature', 'Request')
    # for Station Status Check
    FA_STATION = RequestType(
        'CQ_Monitor/Handshake', 'CQ_Monitor/HandShakeResp', '', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'GETSTATION', 'Request')

    # This is called by reset shim, after FQA testing
    FA_END = RequestType(
        'CQ_Monitor2/Handshak', 'CQ_Monitor2/HandResp', '.OK', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'SWDL', 'Handshake')

    # This is for D2 station.
    FINISH_FQA = RequestType(
        'NL6_Monitor2/Request', 'NL6_Monitor2/Response', '.OK', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'SWDL', 'Request')

    # This is called by reset shim, for 45 station
    FA_END2 = RequestType(
        'NL6_Monitor2/Handshak', 'NL6_Monitor2/HandshakRes', '', None,
        _msdb_host_line[LINE], 'SDT', 'SDT#7', 'QMS', 'MonitorPortal',
        MSDB_BU, 'SWDL', 'Handshake')
    # SMT_START
    SMT_START = RequestType(
        'CQ_Monitor/Handshake', 'CQ_Monitor/HandShakeResp', '', None,
        _msdb_host_line[LINE], 'execuser', 'exec7*user', 'QMS', '[MonitorPortal]',
        MSDB_BU, 'FBT', 'Request')

    # SMT_OA3
    SMT_OA3 = RequestType(
        'CQ_Monitor/Handshake', 'CQ_Monitor2/HandResp', '', None,
        _msdb_host_line[LINE], 'execuser', 'exec7*user', 'QMS', 'MonitorPortal',
        MSDB_BU, 'SetBIOS', 'handshake')

    # SMT_END
    SMT_END = RequestType(
        'CQ_Monitor/Handshake', 'CQ_Monitor/HandShakeResp', '', None,
        _msdb_host_line[LINE], 'execuser', 'exec7*user', 'QMS', 'MonitorPortal',
        MSDB_BU, 'FVT', 'Request')
    ALL = [FA_START, FA_START_FAT, FA_END, FINISH_FQA, FA_END2]


class NewlineTerminatedCSVDialect(csv.excel):
    lineterminator = '\n'


class ShopfloorBackendError(Exception):
    """Exception raised when there is a problem with the backend."""

    pass


class ShopfloorResponseError(Exception):
    """Exception raised when there is a problem with the response."""

    pass


class HTTPShopfloorBackend(object):
    """HTTP-based shopfloor backend.
    This backend uses HTTP post to communicate with shopfloor server.
    """

    def __init__(self):
        self.KEY_SERIAL_NUMBER = KEY_SERIAL_NUMBER
        self.KEY_MLB_SERIAL_NUMBER = KEY_MLB_SERIAL_NUMBER
        self.KEY_HWID = HWID

    @staticmethod
    def FormatTime():
        """Formats the current time for use by the backend."""
        return time.strftime("%Y%m%d%H%M%S", time.localtime())

    @staticmethod
    def TranslateResponse(data):
        """Parses key/value pairs from a response file.
        Invalid lines are logged and ignored.
        Args:
          data: An input string, e.g., 'A=B;$;C=D;$;'
        Returns:
          A dictionary, e.g., {'A': 'B', 'C': 'D'}
        """
        message = {}
        for line in filter(None, data.split(";$;")):
            line = line.rstrip("\n")
            if not line:
                continue
            line = re.sub(r"(?i)^set ", "", line)
            key, equals, value = line.partition("=")
            if equals:
                message[key] = value
            else:
                logging.error("Invalid line %r in response.", line)
        return message

    @staticmethod
    def ConvertToInputStr(message_dict):
        """Converts the message dictionary to input string."""
        if isinstance(message_dict, dict):
            # 1.Send Light Step cannot use below items:
            # 'FANTEST','DLTEST','HDDBOOT','3DMARK','TAT','Thermal','CHKTEMP','Reboot','S4','S3','BTTEST'
            # 2.nextStep can't be before step
            return "".join(["%s=%s;$;" % (k, v) for k, v in sorted(message_dict.items(), reverse=True)])
        else:
            logging.error("Invalid type %r in Inputstr.", type(message_dict))

    def CheckResponse(self, data):
        """Checks if a response indicated pass or failed.
        Args:
          data: A dictionary from raw shopfloor key-value pair.
        """
        result_key_names = ["RESULT", "SF_CFG_CHK", "CheckResult","Check_MB_Result", " Result"]
        err_msg = data.get("ErrMsg") or data.get("ERR_MSG")
        if err_msg and err_msg != "OK":
            raise ShopfloorResponseError("Error %r in response" % err_msg)
        result_keys = [data.get(key) for key in result_key_names]
        result = [string for string in result_keys if string is not None]
        # logging.info("The result keys is %s, result is %s", result_keys, result)
        if not any("PASS" or "OK" in string for string in result):
            raise ShopfloorResponseError(
                "Expected Pass or OK in response, but got %r " % result
            )
        for string in result:
            if "not exist" in string:
                raise ShopfloorResponseError("MB serial number not exist")
        for string in result:
            if "FAIL" in string:
                raise ShopfloorResponseError("the fail is %s" % err_msg)
        return True

    def MappingDeviceData(self, device_data_mapping, message_dict):
        self.CheckResponse(message_dict)
        # Check for missing keys.
        missing_keys = set(device_data_mapping.keys()) - set(message_dict.keys())
        if missing_keys:
            raise ShopfloorResponseError('Missing keys in response: {}'.format(sorted(missing_keys)))

        if isinstance(message_dict, dict):
            response = {
                device_data_mapping[k] if k in device_data_mapping else k: v
                for k, v in message_dict.items()
                if k in device_data_mapping
            }
            is_spare_part = response.get("component.is_spare_part")
            has_sd = response.get("component.has_sd")
            if is_spare_part == "Y":
                response["component.is_spare_part"] = True
            if is_spare_part == "N":
                response["component.is_spare_part"] = False
            if has_sd == "True":
                response["component.has_sd"] = True
            if has_sd == "False":
                response["component.has_sd"] = False
            return response
        else:
            logging.error("Stage Mapping device data error: %s", message_dict)

    def HTTPPost(self, request_type, data, Stage="WEB"):
        """Posts the given data to the shopfloor server and update the device data."""
        # for Retry in range(0,9):#Retry 3 times with each IP

        if Stage == "SQL":
            for i in range(0, len(request_type.msdb_host)):
                logging.info('DEBUG: try to connect HOST %d:%s', i, request_type.msdb_host[i])
                if ping(request_type.msdb_host[i]):
                    serverip = i;
                    break;
            logging.info('DEBUG: connect HOST %d:%s successfully!!', i, request_type.msdb_host[i])
            logging.info("Send request data %s to shopfloor.", data.get("Inputstr"))
            try:
                conn = connect(
                    host=request_type.msdb_host[serverip],
                    user=request_type.msdb_user,
                    password=request_type.msdb_password,
                    database=request_type.msdb_database,
                    login_timeout=300
                )
                sql = """
                  DECLARE @ReturnValue varchar(8000)
                  EXEC %s '%s', '%s', '%s', '%s', @ReturnValue output
                  SELECT @ReturnValue """ % (
                    request_type.msdb_sp, request_type.msdb_bu,
                    request_type.msdb_station, request_type.msdb_step,
                    data.get("Inputstr"),
                )
                cur = conn.cursor()
                cur.execute(sql)
                data = cur.fetchall()[0]
                for i in range(30):
                    ret = cur.nextset()
                    if ret is None:
                        break
                    else:
                        time.sleep(3)
                        data = cur.fetchall()[0]
                conn.commit()
                cur.close()
                data = "".join(str(data[0]))
                logging.info('DEBUG_Call: Shopfloor Response Message is "%s"', data)
            except Exception as e:
                conn.close()
                logging.info("DEBUG: Connect MS Database Error: %s", e)
                time.sleep(3)
                conn = None
            conn.close()  # Release the Server-resource after data interaction
            return self.TranslateResponse(data)

        elif Stage == "WEB":
            for i in range(0, len(request_type.msdb_host)):
                logging.info('DEBUG: try to connect HOST %d:%s', i, request_type.msdb_host[i])
                if Telnet_check(request_type.msdb_host[i], 8080):
                    # "http://10.18.6.41:8080/BatchAPI",
                    serverip = "http://{}:8080/BatchAPI".format(request_type.msdb_host[i])
                    logging.info('DEBUG: connect HOST {} successfully!!'.format(serverip))
                    try:
                        headers = {
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        }
                        # data.update(
                        #     {"BU": request_type.msdb_bu, "Station":request_type.msdb_station , "Step": request_type.msdb_step}
                        # )
                        request_dic = {
                            "BU": request_type.msdb_bu,
                            "Station": request_type.msdb_station,
                            "Step": request_type.msdb_step,
                            "Inputstr": data.get("Inputstr")
                        }
                        logging.info("Send request data %s to shopfloor.", request_dic)
                        response = requests.post(
                            serverip, data=json.dumps(request_dic), headers=headers
                        )
                        response.raise_for_status()
                        response_json = response.json()
                        message = response_json.get("message")
                        unused_result = response_json.get("result")
                        logging.info(
                            "Recived shopfloor response: %s, result %s",
                            message,
                            unused_result,
                        )
                        if unused_result and message:
                            break
                        time.sleep(DELAY_SEC)

                    except Exception as e:
                        logging.info("DEBUG: Connect MS Database Error: %s", e)
                        time.sleep(DELAY_SEC)
            return self.TranslateResponse(message)


class ChromeOSShopfloor(object):
    """Implementation of ChromeOS Factory Shopfloor Service."""

    def __init__(self):
        self.bu = MSDB_BU
        self.backend = HTTPShopfloorBackend()

    def CheckWithSIMCard(self, data):
        SIMCardType = "ESIM"
        WithSIMCard = False
        data = dict(data)
        for key in data.keys():
            if data[key] == '5B965AV':
                WithSIMCard = True
                SIMCardType = "ESIM"
            if data[key] == '5B984AV':
                # startwith 890141032720
                WithSIMCard = True
                SIMCardType = "USIM_ATT"
            if data[key] == '5B985AV':
                # startwith 891480000061
                WithSIMCard = True
                SIMCardType = "USIM_VZW"

        logging.info("Is WithSIMCard:{};CardType is: {}".format(WithSIMCard, SIMCardType))
        return WithSIMCard, SIMCardType

    # Check with 1G1 Manx program matrix
    def CheckPenSlot(self, data):
        has_pen_slot = False
        data = dict(data)
        for key in data.keys():
            if data[key] == '8C8C5AV':
                has_pen_slot = True
            if data[key] == '8C8C4AV':
                has_pen_slot = False
        return has_pen_slot

    # PVT, 2022/03-07, sam
    def PVTConfiguration_DATA_COMMON(self, data):
        if len(data) == 0:
            return data
        logging.info("FakeConfiguration(PVT)...")
        # -------------------------------------
        # Enable ZTE (Sam,2020/12/11)
        if 'serials.serial_number' in data:
            data['vpd.ro.attested_device_id'] = data['serials.serial_number']
        else:
            raise ValueError('Miss serials.serial_number.290')

        # bool: Y/N
        try:
            tablet = True if data['component.branding_name'] == '1G1' else False
            bool_14_inch = True if data['component.branding_name'] == '1G3' else False
            sku_ufs = True if data['component.EMMC_HWID'].upper().find('UFS') >= 0 else False
            sku_mtk = True if data['component.WLAN_HWID'].upper().find('MTK') >= 0 else False
            # sku_kbl = True if data['component.KB_backlight'].upper().find('YES') >= 0 else False
            sku_ts = True if data['component.LCD_HWID'].upper().find('TS') >= 0 else False
            sku_wwan = False if data['component.WWAN_HWID'].upper().find('LTE_NONE') >= 0 else True
            sku_rearcamera = False if data['component.CAMERA_HWID'].upper().find('NO_2ND_CAM') >= 0 or data[
                'component.CAMERA_HWID'].upper().find('NONE') >= 0 else True
        except:
            raise ValueError('Miss info. 377')

        data['component.has_tablet'] = tablet
        data['component.has_touchscreen'] = sku_ts
        data['component.has_14_inch'] = bool_14_inch
        data['component.has_lte'] = sku_wwan
        data['component.has_rear_camera'] = sku_rearcamera
        data['component.has_rearcamera'] = sku_rearcamera
        if sku_ufs:
            storage_type = "UFS"
        else:
            storage_type = "EMMC"

        if sku_mtk:
            wifi_vendor = "MTK"
        else:
            wifi_vendor = "Intel"
        print(sku_rearcamera)
        data['component.has_kblit'] = False

        sku_id = self.SearchCommonTable(tablet, bool_14_inch, sku_ts, sku_wwan, sku_rearcamera, storage_type,
                                        tablet, wifi_vendor)
        data['component.sku'] = sku_id
        logging.info('SKU_ID={}'.format(sku_id))
        data['component.wifi_vendor'] = wifi_vendor
        data['component.storage_type'] = storage_type

        # if data['factory.FQA_Flag'] == 'Y':
        #    data['factory.status.fqa'] = True
        # else:
        #    data['factory.status.notfqa'] = True

        return data

    def SearchCommonTable(self, has_tablet, has_14_inch, has_touchscreen, has_lte, has_rear_camera, storage, has_stylus,
                          wifi_vendor):
        data1 = mbpn_to_rampn.DATA_SKUID
        data2 = []
        for i in range(len(data1)):
            (sku_id, fw_config, sku_tablet, sku_14_inch, sku_touchscreen, sku_lte, sku_rear_camera, sku_storage,
             sku_stylus, sku_wifi_vendor, comment) = data1[i]
            if ((has_tablet == sku_tablet) and
                    (has_14_inch == sku_14_inch) and
                    (has_touchscreen == sku_touchscreen) and
                    (has_lte == sku_lte) and
                    (has_rear_camera == sku_rear_camera) and
                    (storage.upper() == sku_storage.upper()) and
                    (has_stylus == sku_stylus) and
                    (wifi_vendor.upper() == sku_wifi_vendor.upper())):
                data2 += [data1[i]]
        # -------------------------------------

        # Determine if there is a SKU ID that meets the criteria
        if data2 == []:
            raise ValueError('Error: sku id miss.379')

        (sku_id, fw_config, sku_tablet, sku_14_inch, sku_touchscreen, sku_lte, sku_rear_camera, sku_storage, sku_stylus,
         sku_wifi_vendor, comment) = data2[0]

        logging.info('SKU_ID={} SKU={}'.format(sku_id, comment))
        return sku_id

    def SearchPNTable(self, data):
        if 'component.quanta_pn' not in data:
            return data
        #
        logging.info("SearchCommonTable...")

        # -------------------------------------
        sku_kbl = True if data['component.KB_backlight'].upper().find('YES') >= 0 else False
        data1 = mbpn_to_rampn.DATA_DVT
        data2 = []
        for i in range(len(data1)):
            (table_first_PN, model, mb_pn, ramvendor, dram_part_num, cpu_hwid, ramsize, emmc_ufs_size, tablet,
             touchscreen, bool_14_inch, bool_wwan, bool_rear_camera, region, storage_type, has_stylus, wifi_vendor, sku,
             dlm_sku_id) = data1[i]
            if ((table_first_PN == data['component.quanta_pn'])):
                data2 += [data1[i]]
        # -------------------------------------,

        # Determine if there is a SKU ID that meets the criteria
        if data2 == []:
            raise ValueError('Error: first PN miss')
        (table_first_PN, model, mb_pn, ramvendor, dram_part_num, cpu_hwid, ramsize, emmc_ufs_size, tablet, touchscreen,
         bool_14_inch, bool_wwan, bool_rear_camera, region, storage_type, has_stylus, wifi_vendor, sku, dlm_sku_id) = \
        data2[0]
        data['component.dram_part_num'] = dram_part_num
        data['component.CPU_HWID'] = cpu_hwid
        data['component.DRAM_HWID'] = ramsize
        data['component.EMMC_HWID'] = emmc_ufs_size
        data['component.has_tablet'] = tablet
        data['component.has_touchscreen'] = touchscreen
        data['component.has_14_inch'] = bool_14_inch
        data['component.has_lte'] = bool_wwan
        data['component.has_rear_camera'] = bool_rear_camera
        data['component.storage_type'] = storage_type
        data['component.has_stylus'] = has_stylus
        data['component.wifi_vendor'] = wifi_vendor
        data['factory.sku'] = sku
        data['vpd.ro.region'] = region
        data['component.has_kblit'] = sku_kbl
        data['vpd.ro.dlm_sku_id'] = dlm_sku_id

        sku_id = self.SearchCommonTable(tablet, bool_14_inch, touchscreen, bool_wwan, bool_rear_camera, storage_type,
                                        tablet, wifi_vendor)
        data['component.sku'] = sku_id
        logging.info('SKU_ID={} SKU={}'.format(sku_id, sku))
        return data

        # PVT, 2022/09-10, sam

    def MyKeyboardLayoutTable(self, r1):
        # Use table for keyboard layout check. (Sam,2022/08)
        # Input: us, gb, jp, ....
        # Output: ISO, ANSI, JIS

        logging.info('MyKeyboardLayoutTable.')

        if r1 in mbpn_to_rampn.COUNTRY_VS_KEYBOARD:
            kb_layout = mbpn_to_rampn.COUNTRY_VS_KEYBOARD[r1]
            logging.info('Keyboard: region={}. keyboard_layout={}.'.format(
                r1, kb_layout))
        else:
            raise ValueError('Error: Miss info for keyboard layout.')

        return kb_layout

    @staticmethod
    def MbpnToRampn(self, data):
        # MBPN to RAMPN
        """Find RAM PN from NB PN"""
        if 'factory.mb_pn' not in data:
            return data
        if data['factory.mb_pn'] in mbpn_to_rampn.MBPN_TO_RAMPN:
            data['component.dram_part_num'] = mbpn_to_rampn.MBPN_TO_RAMPN[data['factory.mb_pn']]
        else:
            raise ShopfloorResponseError("MBPN={} not in mbpn table ".format(data['factory.mb_pn']))
        return data

    @staticmethod
    def SearchLCDPNTable(self, data):

        if 'component.LCDPN' not in data:
            return data
        data1 = mbpn_to_rampn.LCDPN_TO_LCDPID
        data2 = []
        for i in range(len(data1)):
            (TOP_PN, QBCON_PN, PID, Vendor, remark) = data1[i]
            if ((TOP_PN == data['component.LCDPN'])):
                data2 += [data1[i]]
        if data2 == []:
            raise ShopfloorResponseError("LCDPN={} not in LCDPN_TO_LCDPID table ".format(data['component.LCDPN']))

        (TOP_PN, QBCON_PN, PID, Vendor, remark) = data2[0]
        data['component.chrome_lcd_pid'] = Vendor + PID

        return data

    @staticmethod
    def FixedKey(self, data):
        """Keys that is fixed for this project"""
        """data['vpd.rw.gbind_attribute'] = '33333333333333333333333333333333333333333333333333333333333333332dbecc73'
        data['vpd.rw.ubind_attribute'] = '323232323232323232323232323232323232323232323232323232323232323256850612'
        return data
        """
        return data

    def RandomSample(self):
        if random.randint(0, 99) % 3 == 0:
            return True
        else:
            return False

    @staticmethod
    def PVTConfiguration(self, data):
        if len(data) == 0:
            return data
        return self.PVTConfiguration_DATA_COMMON(data)

    def SMTStart(self,data):
	data['factory.ethernet_mac0'] = data['factory.ethernet_mac0'].replace(":","")
        inputstr_dict = {
            "MB_NUM": data["serials.mlb_serial_number"],
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "OPID": data['factory.smt_operator_id'],
            "MAC": data['factory.ethernet_mac0'],
            "STATION": "FBT",
            "RESULT": "PASS",
            "FULLTEST": "Y",
            "Fixture": data['factory.smt_station_id']
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.SMT_START, data, Stage)

        # Translate shopfloor fields into the types we expect.
        key_translation = {
            # 'Registration_Code': 'vpd.rw.ubind_attribute',
            # 'Group_code': 'vpd.rw.gbind_attribute',
            'CPU': 'component.CPU',  # adam0904++
            #'eMMC_Size': 'component.eMMC_Size',
            'ModelN': 'factory.quanta_name',
            #'RAMTP': 'component.RAMTP',  # adam++
            # 'RAM_PN': 'component.dram_part_num', # SMT
            # 'WWAN': 'component.WWAN',  # adam++
            #'RAMMODEL': 'component.dram_part_num',  # SMT
            # 'CBI': 'factory.boardver', #SMT add 2021/03/28
        }
        ret = self.backend.MappingDeviceData(key_translation, _response)

        #if 'component.dram_part_num' not in ret:
        #    raise ValueError('RAM_PN is missing.')
        # if ret['component.WWAN'] == 'YES':
        #   ret['component.has_lte']=True
        # else:
        #   ret['component.has_lte']=False

        if not ret['factory.quanta_name'] in ['0WI']:
            raise ShopfloorResponseError('Error Model in response: %s' % ret['factory.quanta_name'])
        return ret

    def SMTEnd(self,data):
	data['factory.ethernet_mac0'] = data['factory.ethernet_mac0'].replace(":","")
        inputstr_dict = {
            "MB_NUM": data["serials.mlb_serial_number"],
            # "BT_MAC": data["factory.bluetooth_mac"],
            "OPID": data["factory.smt_operator_id"],
            "Fixture": data["factory.smt_station_id"],
            "MAC": data['factory.ethernet_mac0'],
            # "Registration_Code":data["vpd.rw.ubind_attribute"],
            # "Group_code":data["vpd.rw.gbind_attribute"],
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "STATION": "FVT",
            "RESULT": "PASS",
            "FULLTEST": "Y",
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.SMT_END, data, Stage)
        key_translation = {'Check_MB_Result': 'factory.Result', }
        ret = self.backend.MappingDeviceData(key_translation, _response)

        # SP_OA3 T3 staion
        # time.sleep(3)
        # inputstr_dict = {
        #     "MB_NUM": data["serials.mlb_serial_number"],
        #     #"BT_MAC": data["factory.bluetooth_mac"],
        #     "OPID": data["factory.smt_operator_id"],
        #     "Fixture": data["factory.smt_station_id"],
        #     #"Registration_Code":data["vpd.rw.ubind_attribute"],
        #     #"Group_code":data["vpd.rw.gbind_attribute"],
        #     "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
        #     "MACID": "",
        # }
        # inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        # data.update(
        #     {"Inputstr": inputstr}
        # )
        # _response = self.backend.HTTPPost(RequestTypes.SP_OA3,data,Stage)
        # key_translation = {'Result': 'factory.Result', }
        # ret = self.backend.MappingDeviceData(key_translation,_response)

        return ret

    def FATStart(self, data):  # D1 Station
        inputstr_dict = {
            "BATCT_NUM": data['factory.battct_num'],
            'DL_SWITCHIP': data['factory.switchip'],
            'DL_PORT': data['factory.switchport'],
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.FA_START, data, Stage)
        """Maps the device data to the key names."""
        key_translation = {
            # ----------------------   BIOS value  Start ----------------------
            'SN': 'serials.serial_number',
            'MB_SN': 'serials.mlb_serial_number',
            'Registration_Code': 'vpd.rw.ubind_attribute',
            'Group_code': 'vpd.rw.gbind_attribute',
            'SKU': 'vpd.ro.sku_number',  # DUT region code
            'KB_layout': 'vpd.ro.region',  # DUT region code
            'BIOSBrand': 'vpd.ro.model_name',  # DUT BIOS branding name
            # ----------------------   BIOS value  End ----------------------

            'LINE': 'factory.line',  # Production Line
            'HPPN': 'component.quanta_pn',  # Quanta 1st PN
            'MBPN': 'factory.mb_pn',  # FA
            # 'FQA_Flag': 'factory.FQA_Flag',
            # 'MODEL': 'factory.quanta_model',# Quanta model name
            'MODEL': 'component.branding_name',
            'WO': 'factory.WO',  # Work Order
            # 'MARK': 'factory.phase',  # Stage: SI/PV/MV
            'BacklightKB': 'component.KB_backlight',
            # ----------------------   NEW HWID process  Start ----------------------

            'LCD_HWID': 'component.LCD_HWID',
            'HDD1_HWID': 'component.HDD1_HWID',
            'EMMC_HWID': 'component.EMMC_HWID',
            'DRAM_HWID': 'component.DRAM_HWID',
            'CPU_HWID': 'component.CPU_HWID',
            'GPU_HWID': 'component.EXT_VR',  # Check if the EXT_VR is or not
            'IMR1_HWID': 'component.IMR1_HWID',
            'IMR2_HWID': 'component.IMR2_HWID',
            'WWAN_HWID': 'component.WWAN_HWID',
            'CAMERA_HWID': 'component.CAMERA_HWID',
            'WLAN_HWID': 'component.WLAN_HWID',
            'LCDPN': 'component.LCDPN',
            'BAT_HWID': 'component.batt_capacity',
            # ----------------------   NEW HWID process  End ----------------------

            # ----------------------   old HWID process  Start ----------------------
            # 'aux1': 'component.ssdsize',
            # 'aux2': 'component.ramsize',  # adam++
            # 'GBU_CPU': 'component.GBU_CPU',  # adam0904++
            # 'mechanical': 'factory.camera',
            # 'mechanical2': 'factory.camera2',
            # 'display_size': 'component.display_type',
            # 'WWAN': 'component.has_lte',
            # 'KB_SN': 'component.kb_sn',
            # ----------------------   old HWID process  end ----------------------
            # 'Widevine_DeviceID': 'factory.widevine_device_id', #0GS need widevine keybox
            # 'Widevine_CRC': 'factory.widevine_crc',
            # 'Widevine_ID': 'factory.widevine_id',
            # 'Widevine_Key': 'factory.widevine_key',
            # 'Widevine_Magic': 'factory.widevine_magic',
        }
        # add for D1/D2 power saving.
        if 'D1SleepStart' in set(_response.keys()):
            key_translation['D1SleepStart'] = 'factory.D1sleepstart'
        if 'D1SleepKeep' in set(_response.keys()):
            key_translation['D1SleepKeep'] = 'factory.D1sleepkeep'
        ret = self.backend.MappingDeviceData(key_translation, _response)

        has_pen_slot = self.CheckPenSlot(_response)
        ret['component.has_stylus'] = has_pen_slot

        ret = self.PVTConfiguration(self, ret)
        ret = self.MbpnToRampn(self, ret)
        ret = self.SearchLCDPNTable(self, ret)
        # ret = self.FixedKey(self, ret)

        return ret

    def DTStart(self, data):  # DT Station
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "SN": data["serials.serial_number"],
            "MBSN": data["serials.mlb_serial_number"],
            "ErrCode": "PASS",
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.FA_START_FAT, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def FRTStart(self, data):  # 25 Station
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "SN": data["serials.serial_number"],
            "MBSN": data["serials.mlb_serial_number"],
            "ErrCode": "PASS",
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.FA_START_FRT, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def FATEnd(self, data):
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "SN": data["serials.serial_number"],
            "MBSN": data["serials.mlb_serial_number"],
            "ErrCode": "PASS",
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.FA_END, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def D1YellowLight(self, data):  # D1 Yellow Light
        step = "DLPASS"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            "STEP": step,
            "NEXTSTEP": "HWCHECK",
            "INTERVAL": "10",
            "ERRORCODE": "Ongoing",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": step, "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def HWCheckYellowLight(self, data):  # D1 Yellow Light
        step = "HWCHECK"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            "STEP": step,
            "NEXTSTEP": "DTPass",
            "INTERVAL": "10",
            "ERRORCODE": "Ongoing",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": step, "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def DTGreenLight(self, data):  # DT Green Light
        step = "DTPass"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            "STEP": step,
            "NEXTSTEP": "WAITOFFLINE",
            "INTERVAL": "280000",
            "ERRORCODE": "PASS",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": step, "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def DTBlueLight(self, data):  # DT Blue Light
        step = "WAITOFFLINE"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            "STEP": step,
            "NEXTSTEP": "PQCTEST",
            "INTERVAL": "280000",
            "ERRORCODE": "offline",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": step, "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def D1RedLight(self, data):  # FAT Red Light
        step = "WAITOFFLINE"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            "STEP": step,
            "NEXTSTEP": "PQCTEST",
            "INTERVAL": "28000",
            "ERRORCODE": "fail",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": step, "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def PQCRedLight(self, data):  # PQC Red Light
        step = "WAITOFFLINE"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            "STEP": "PQCTEST",
            "NEXTSTEP": "RUNIN",
            "INTERVAL": "28000",
            "ERRORCODE": "fail",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": step, "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def RunInYellowLight(self, data):
        step = "Stresstest"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            "STEP": step,
            "NEXTSTEP": "S3",
            "INTERVAL": "600",
            "ERRORCODE": "Ongoing",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": step, "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def RunInRedLight(self, data):  # FAT Red Light
        step = "WAITOFFLINE"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            "STEP": "Stresstest",
            "NEXTSTEP": "RUNIN",
            "INTERVAL": "28000",
            "ERRORCODE": "fail",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": step, "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def GRTYellowLight(self, data):
        step = "Finalize"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            "STEP": step,
            "NEXTSTEP": "Wiping",
            "INTERVAL": 15,
            "ERRORCODE": "Ongoing",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": step, "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def GRTRedLight(self, data):  # FAT Red Light
        step = "Finalize"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            "STEP": step,
            "NEXTSTEP": "Wiping",
            "INTERVAL": "28000",
            "ERRORCODE": "fail",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": step, "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def TempUpload(self, data):  # Upload CPU temp
        if 'factory.cpu_temp' not in data:
            data['factory.cpu_temp'] = ""
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "SN": data["serials.serial_number"],
            'TempType': 'CPU',
            'Temp': data['factory.cpu_temp'],
            'Spec': RUNIN_TEMP_SPEC,
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": "Request", "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.FA_START_TEMP, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        return ret

    def D2Station(self, data):  # FQA Send D2 Station

        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            'MB': data['serials.mlb_serial_number'],
            'MOTHERBRD_SN': data['serials.mlb_serial_number'],
            'MB_SN': data['serials.mlb_serial_number'],
            'HWID': data['hwid'],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": "Request", "Inputstr": inputstr}
        )
        _response = self.backend.HTTPPost(RequestTypes.FA_STATION, data, Stage)
        key_translation = {'STATION': 'STATION', }
        ret = self.backend.MappingDeviceData(key_translation, _response)
        if ret.get("STATION") == "RT":
            raise ShopfloorResponseError('D2 will not receive RT for chromebook!')
        else:
            _response = self.backend.HTTPPost(RequestTypes.FINISH_FQA, data, Stage)

            key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK',
                               'Model': 'factory.branding_name', }
            ret = self.backend.MappingDeviceData(key_translation, _response)
            if not ret['factory.branding_name'] in ['0WI']:
                raise ShopfloorResponseError(
                    'Error Model Name in response: %s,Please Use Right USB Re-Download' % ret['factory.branding_name'])
            return ret

    def FFTStart(self, data):
        return self.DUMMY(data, "DUMMY")

    def FFTEnd(self, data):
        return self.DUMMY(data, "DUMMY")

    def RUNINStart(self, data):
        return self.DUMMY(data, "DUMMY")

    def RUNINEnd(self, data):
        return self.DUMMY(data, "DUMMY")

    def GRTStart(self, data):
        return self.DUMMY(data, "DUMMY")

    # RT station
    def GRTEnd(self, data):  # RT Station
        if 'factory.esim_id' not in data:
            data['factory.esim_id'] = ""
        if 'factory.usim_iccid' not in data:
            data['factory.usim_iccid'] = ""
        if 'factory.wwan_imei' not in data:
            data['factory.wwan_imei'] = ""
        if 'factory.wwan_esim_eid' not in data:
            data['factory.wwan_esim_eid'] = ""
        inputstr = {
            "ERRCode": "PASS",
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "MB": data["serials.mlb_serial_number"],
            "MACID": "NOMAC",
            "Serial_Number": data["serials.serial_number"],
            'WL_MAC': data['factory.wlan_mac'],
            'BT_MAC': data['factory.bt_mac'],
            'IMEI': data['factory.wwan_imei'],
            'eSIM_ID': data['factory.wwan_esim_eid'],
            'ICCID': data['factory.usim_iccid'],
            'IMAGE_VER': data['factory.release_ver'],
            'BIOS_VER': data['factory.bios_ver'],
            'Google_HWID': data['factory.hwid'],
            'GOOGLE_CODE_NAME': data['factory.google_name'],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr)
        data.update(
            {"Step": "Request", "Inputstr": inputstr}
        )
        response = self.backend.HTTPPost(RequestTypes.FA_START_RT, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        # add for D1/D2 power saving.
        if 'RTSleepStart' in set(response.keys()):
            key_translation['RTSleepStart'] = 'factory.RTsleepstart'
        if 'RTSleepKeep' in set(response.keys()):
            key_translation['RTSleepKeep'] = 'factory.RTsleepkeep'
        ret = self.backend.MappingDeviceData(key_translation, response)
        return ret

    def Finalized(self, data):  # 45 Station
        _ret = "SHOPFLOORPASS"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            'MB': data['serials.mlb_serial_number'],
            'MOTHERBRD_SN': data['serials.mlb_serial_number'],
            'MB_SN': data['serials.mlb_serial_number'],
            'HWID': data['hwid'],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": "Request", "Inputstr": inputstr}
        )
        response = self.backend.HTTPPost(RequestTypes.FA_END2, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, response)
        time.sleep(3)

        response = self.backend.HTTPPost(RequestTypes.FA_STATION, data, Stage)
        key_translation = {'STATION': 'STATION', }
        ret = self.backend.MappingDeviceData(key_translation, response)

        if ret['STATION'] == "5Q" or ret['STATION'] == "5C" or ret['STATION'] == "5R":
            _ret = "5QSHOPFLOORPASS"
            inputstr_dict = {
                "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
                'Step': 'Wiping',
                'NextStep': '45station',
                'Interval': '280000',
                'ErrorCode': 'FQA',
                "Serial_Number": data["serials.serial_number"],
                'MB_SN': data['serials.mlb_serial_number'],
            }
            inputstr = self.backend.ConvertToInputStr(inputstr_dict)
            data.update(
                {"Step": "Request", "Inputstr": inputstr}
            )
            _response = self.backend.HTTPPost(
                RequestTypes.LIGHT, data, Stage)
        elif ret['STATION'] == "45":
            _ret = "45SHOPFLOORPASS"
            inputstr_dict = {
                "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
                'Step': 'Wiping',
                'NextStep': '45station',
                'Interval': '280000',
                'ErrorCode': 'PASS',
                "Serial_Number": data["serials.serial_number"],
                'MB_SN': data['serials.mlb_serial_number'],
            }
            inputstr = self.backend.ConvertToInputStr(inputstr_dict)
            data.update(
                {"Step": "Request", "Inputstr": inputstr}
            )
            _response = self.backend.HTTPPost(
                RequestTypes.LIGHT, data, Stage)

        return _ret

    def FinalizedFQA(self, data):  # D2 Station
        _ret = "SHOPFLOORPASS"
        inputstr_dict = {
            "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
            "Serial_Number": data["serials.serial_number"],
            'MB': data['serials.mlb_serial_number'],
            'MOTHERBRD_SN': data['serials.mlb_serial_number'],
            'MB_SN': data['serials.mlb_serial_number'],
            'HWID': data['hwid'],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"Step": "Request", "Inputstr": inputstr}
        )
        response = self.backend.HTTPPost(RequestTypes.FINISH_FQA, data, Stage)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, response)
        time.sleep(3)
        response = self.backend.HTTPPost(RequestTypes.FA_END2, data, Stage)
        logging.info("CheckDUTStatus: %s", data)
        key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
        ret = self.backend.MappingDeviceData(key_translation, response)

        return _ret

    def DUMMY(self, *args, **kargs):
        logging.info("Dummy API invoked %r %r.", args, kargs)
        return {}


class ShopfloorService:
    def __init__(self):
        self.middleware = ChromeOSShopfloor()

    def GetVersion(self):
        """Returns the version of supported protocol."""
        return "3.0.1"

    def _Dispatch(self, data, key, mapping):
        """The dispatch for factory process."""
        targets = mapping[key]
        if callable(targets):
            targets = [targets]
        for target in targets:
            last = target(data)
        return last or {}

    def NotifyStart(self, data, station):
        """Notifies shopfloor backend that DUT is starting a manufacturing station.

        Args:
            data: A FactoryDeviceData instance.
            station: A string to indicate manufacturing station.

        Returns:
            A mapping in DeviceData format.
        """
        mapping = {
            "SMT": self.middleware.SMTStart,
            "FAT": self.middleware.DTStart,
            "FRT": self.middleware.FRTStart,
            "FATPYellowLight": self.middleware.D1YellowLight,
            "FATPGreenLight": self.middleware.DTGreenLight,
            "FATPBlueLight": self.middleware.DTBlueLight,
            "FATRedLight": self.middleware.D1RedLight,
            "FFT": self.middleware.FFTStart,
            "FFTRedLight": self.middleware.PQCRedLight,
            "FAUploadTemp": self.middleware.TempUpload,
            "RUNINYellowLight": self.middleware.RunInYellowLight,
            "RUNINRedLight": self.middleware.RunInRedLight,
            "FQAReFinalize": self.middleware.D2Station,
            "GRT": self.middleware.GRTStart,
            "GRTRedLight": self.middleware.GRTRedLight,
            "GRTYellowLight": self.middleware.GRTYellowLight,
            "SendRedLight": self.middleware.D1RedLight,
        }

        return self._Dispatch(data, station, mapping)

    def NotifyEnd(self, data, station):
        """Notifies shopfloor backend that DUT has finished a manufacturing station.
        Args:
            data: A FactoryDeviceData instance.
            station: A string to indicate manufacturing station.
        Returns:
            A mapping in DeviceData format.
        """
        mapping = {
            "SMT": self.middleware.SMTEnd,
            "FAT": self.middleware.FATEnd,
            "FFT": self.middleware.FFTEnd,
            "RUNIN": self.middleware.RUNINEnd,
            "GRT": self.middleware.GRTEnd,
        }
        return self._Dispatch(data, station, mapping)

    def NotifyEvent(self, data, event):
        """Notifies shopfloor backend that the DUT has performed an event.

        Args:
          data: A FactoryDeviceData instance.
          event: A string to indicate manufacturing event.

        Returns:
          A mapping in FactoryDeviceData format.
        """
        assert event in ["Finalize", "Refinalize"]
        event_mapping = {
            "Finalize": self.middleware.Finalized,
            "Refinalize": self.middleware.FinalizedFQA,
        }
        return self._Dispatch(data, event, event_mapping)

    def GetDeviceInfo(self, data):
        """Returns information about the device's expected configuration.

        Args:
          data: A FactoryDeviceData instance.

        Returns:
          A mapping in DeviceData format.
        """
        return self.middleware.FATStart(data)

    def ActivateRegCode(self, ubind_attribute, gbind_attribute, hwid):
        """Notifies shopfloor backend that DUT has deployed a registration code.
        Args:
          ubind_attribute: A string for user registration code.
          gbind_attribute: A string for group registration code.
          hwid: A string for the HWID of the device.

        Returns:
          A mapping in FactoryDeviceData format.
        """
        logging.info('DUT <hwid=%s> requesting to activate regcode(u=%s,g=%s)',
                     hwid, ubind_attribute, gbind_attribute)

        # default implementation, let's log it in a CSV file
        # See http://goto/nkjyr for file format.
        if not hwid:
            raise ValueError('HWID is missing.')
        board = hwid.partition(' ')[0]

        with open(REGCODE_LOG_CSV, 'ab') as f:
            csv.writer(f, dialect=NewlineTerminatedCSVDialect).writerow([
                board,
                ubind_attribute,
                gbind_attribute,
                time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()),
                hwid])
            os.fdatasync(f.fileno())

        return {}

    def UpdateTestResult(self, data, test_id, status, details=None):
        """Sends the specified test result to shopfloor backend.

        Args:
          data: A FactoryDeviceData instance.
          test_id: A string as identifier of the given test.
          status: A string from TestState; one of PASSED, FAILED, SKIPPED, or
              FAILED_AND_WAIVED.
          details: (optional) A mapping to provide more details, including at least
              'error_message'.

        Returns:
          A mapping in DeviceData format. If 'action' is included, DUT software
          should follow the value to decide how to proceed.
        """
        logging.info(
            "DUT %s updating test results for <%s> with status <%s> %s",
            data.get("serials.serial_number"),
            test_id,
            status,
            details.get("error_message") if details else "",
        )
        step = None
        for _test_id in test_id:
            step = _test_id.split(".")[-1]
        if step:
            inputstr_dict = {
                "MonitorAgentVer": Stage_MonitorAgentVer[Stage],
                "Serial_Number": data["serials.serial_number"],
                "STEP": step,
                "INTERVAL": "10",
                "ERRORCODE": "fail",
                "DL_SWITCHIP": data["factory.switchip"],
                "DL_PORT": data["factory.switchport"],
            }
            inputstr = self.middleware.backend.ConvertToInputStr(inputstr_dict)
            data.update(
                {"Step": step, "Inputstr": inputstr}
            )
            _response = self.middleware.backend.HTTPPost(RequestTypes.LIGHT_UPDATE, data, Stage)
            key_translation = {'SF_CFG_CHK': 'factory.SF_CFG_CHK', }
            ret = self.middleware.backend.MappingDeviceData(key_translation, _response)
            return ret


def Now():
    """Returns the current time (may be stubbed out)."""
    return time.time()


def FormatBackendTime():
    """Formats the current time for use by the backend."""
    return time.strftime('%Y%m%d%H%M%S', time.localtime(Now()))


def FormatTime():
    """Formats the current time."""
    return time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(Now()))


class ThreadedXMLRPCServer(SocketServer.ThreadingMixIn,
                           SimpleXMLRPCServer.SimpleXMLRPCServer):
    """A threaded XML RPC Server."""
    pass


def RunAsServer(address, port, instance, logRequest=False):
    '''Starts a XML-RPC server in given address and port.

    Args:
      address: Address to bind server.
      port: Port for server to listen.
      instance: Server instance for incoming XML RPC requests.
      logRequests: Boolean to indicate if we should log requests.

    Returns:
      Never returns if the server is started successfully, otherwise some
      exception will be raised.
    '''
    server = ThreadedXMLRPCServer((address, port), allow_none=True,
                                  logRequests=logRequest)
    server.register_introspection_functions()
    server.register_instance(instance)
    logging.info('Server started: http://%s:%s "%s" version %s',
                 address, port, instance.__class__.__name__,
                 instance.GetVersion())
    server.serve_forever()


def main():
    """Main entry when being invoked by command line."""
    parser = optparse.OptionParser()
    parser.add_option('-a', '--address', dest='address', metavar='ADDR',
                      default=DEFAULT_SERVER_ADDRESS,
                      help='address to bind (default: %default)')
    parser.add_option('-p', '--port', dest='port', metavar='PORT', type='int',
                      default=DEFAULT_SERVER_PORT,
                      help='port to bind (default: %default)')
    parser.add_option('-d', '--dir', dest='dir', metavar='DIR',
                      default=DEFAULT_ROOT_DIR,
                      help='root dir for shared drive (default: %default)')
    parser.add_option('-v', '--verbose', dest='verbose', default=False,
                      action='store_true',
                      help='provide verbose logs for debugging.')
    (options, args) = parser.parse_args()
    if args:
        parser.error('Invalid args: %s' % ' '.join(args))

    log_format = '%(asctime)s %(levelname)s %(message)s'
    logging.basicConfig(level=logging.DEBUG if options.verbose else logging.INFO,
                        format=log_format)

    # Disable all DNS lookups, since otherwise the logging code may try to
    # resolve IP addresses, which may delay request handling.
    socket.getfqdn = lambda(name): name or 'localhost'

    try:
        RunAsServer(address=options.address, port=options.port,
                    instance=ShopfloorService(),
                    logRequest=options.verbose)
    finally:
        logging.warn('Server stopped.')


if __name__ == '__main__':
    main()
