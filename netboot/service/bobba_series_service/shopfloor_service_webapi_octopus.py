#!/usr/bin/env python3.5
#
# Copyright 2023 The ChromiumOS Authors
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
# Author: Huanhuan Liu (huanhuanl@chromium.org)
# Date: Thu Nov 14 22:07 2023

"""Implementation of ChromeOS Factory Shopfloor Service, version 3.0.1"""

import re
import json
import time
import socket
import logging
import requests
import argparse
import socketserver
import xmlrpc.server
from pymssql import connect

DEFAULT_SERVER_PORT = 10060
DEFAULT_SERVER_ADDRESS = "0.0.0.0"
url = [
    "http://10.18.6.41:8080/BatchAPI",
    "http://10.18.6.42:8080/BatchAPI",
    "http://10.18.6.50:8080/BatchAPI",
]
SMT_url = "10.18.8.11"
MAX_RETRIES_TIMES = 3
DELAY_SEC = 3

KEY_SERIAL_NUMBER = "serials.serial_number"
KEY_MLB_SERIAL_NUMBER = "serials.mlb_serial_number"
HWID = "hwid"

DataBase_Port = "NB4"
DataBase_SP = "MonitorPortal"
DataBase_Group = ["SMT", "QMS"]
Login_User = ["SDT", "execuser"]
Login_Password = ["SDT#7", "exec7*user"]


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
            return "".join(["%s=%s;$;" % (k, v) for k, v in message_dict.items()])
        else:
            logging.error("Invalid type %r in Inputstr.", type(message_dict))

    def CheckResponse(self, data):
        """Checks if a response indicated pass or failed.
        Args:
          data: A dictionary from raw shopfloor key-value pair.
        """
        result_key_names = ["RESULT", "SF_CFG_CHK", "CheckResult", " Result"]
        err_msg = data.get("ErrMsg") or data.get("ERR_MSG")
        if err_msg and err_msg != "OK":
            raise ShopfloorResponseError("Error %r in response" % err_msg)
        result_keys = [data.get(key) for key in result_key_names]
        result = [string for string in result_keys if string is not None]
        logging.info("The result keys is %s, result is %s", result_keys, result)
        if not any("PASS" or "OK" in string for string in result):
            raise ShopfloorResponseError(
                "Expected Pass or OK in response, but got %r " % result
            )
        for string in result:
            if "not exist" in string:
                raise ShopfloorResponseError("MB serial number not exist")
        for string in result:
            if "FAIL" in string:
                raise ShopfloorResponseError("the fail is %s" %  err_msg)
        return True

    def MappingDeviceData(self, data):
        """Maps the device data to the key names."""
        device_data_mapping = {
            "Work_Order": "factory.Work_Order",
            "QCI_Model": "factory.Quanta_Project_Name",
            "HWID": self.KEY_HWID,
            "MB_NUM": self.KEY_MLB_SERIAL_NUMBER,
            "User_code": "vpd.rw.ubind_attribute",
            "Group_code": "vpd.rw.gbind_attribute",
            "Region_Code": "vpd.ro.region",
            "SN": self.KEY_SERIAL_NUMBER,
            "LCD": "component.lcd_type",
            "gbu_type": "component.cpu_type",
            "chrome_lcd_pid": "component.chrome_lcd_pid",
            "SparePart": "component.is_spare_part",
            "ALL_RAM_SIZE": "component.ram_size",
            "VendorID": "component.dram.part_num",
            "eMMcHDD_Szie": "component.storage_size",
            "eMMcHDD_Szie": "component.hdd_size",
            "InputDateTime": "factory.input_time",
            "LINE": "factory.line",
            "PMIC": "vpd.ro.sku_number",
            "HAS_SD": "component.has_sd",
            "SKUID": "component.sku",
        }

        message_dict = self.TranslateResponse(data)
        self.CheckResponse(message_dict)
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
            logging.info("Stage Mapping device data: %s", response)
            return response
        else:
            logging.error("Stage Mapping device data error: %s", message_dict)

    def HTTPPost(self, data):
        """Posts the given data to the shopfloor server and update the device data."""
        # for Retry in range(0,9):#Retry 3 times with each IP
        if "STATION=FVS" in data:
            STATION = "FVS"
            print("*******************************Request Info As Below************************************")
            print(data)
            if "Request" in data:
                MSDB_STEP = "Request"
            if "Handshake" in data:
                MSDB_STEP = "Handshake"
                  
            try:
                conn = connect(
                    host=SMT_url,
                    user=Login_User[1],
                    password=Login_Password[1],
                    database=DataBase_Group[0],
                    login_timeout=300,
                )
                sql = """
                  DECLARE @ReturnValue varchar(8000)
                  EXEC %s '%s', '%s', '%s', '%s', @ReturnValue output
                  SELECT @ReturnValue """ % (
                    DataBase_SP,
                    DataBase_Port,
                    STATION,
                    MSDB_STEP,
                    data,
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
            response = data
            print(response)
            if len(response) == 0:
                return
            else:
                 message = response
                 response_format = self.TranslateResponse(response)
                 self.CheckResponse(response_format)
                 print("*************************************************")
                 print(response_format)
            print(message)
            return self.MappingDeviceData(message)

        else:
            for Retry in range(0, len(url) * MAX_RETRIES_TIMES):
            #for Retry in range(0, len(url)):
                try:
                    headers = {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    }
                    logging.info("Send request data %s to shopfloor.", data)
                    response = requests.post(
                        url[Retry], data=json.dumps(data), headers=headers
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
                except Exception as e:
                    logging.info("DEBUG: Connect MS Database Error: %s", e)
                    time.sleep(DELAY_SEC)
                return self.MappingDeviceData(message)


class ChromeOSShopfloor(object):
    """Implementation of ChromeOS Factory Shopfloor Service."""

    def __init__(self):
        self.bu = "STN"
        self.backend = HTTPShopfloorBackend()

    def SMTStart(self, data):
        inputstr_dict = {
            "STATION": "FVS",
            "MB_NUM": data["serials.mlb_serial_number"],
            "MSDB_STEP": "Request",
            "MonitorAgentVer": "VL20151102.01",
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        return self.backend.HTTPPost(inputstr)

    def SMTEnd(self, data):
        inputstr_dict = {
            "STATION": "FVS",
            "MB_NUM": data["serials.mlb_serial_number"],
            "onboard_wifi": "true",
            "WLANID": data["factory.wifi_mac"],
            "BT_MAC": data["factory.bluetooth_mac"],
            "MSDB_STEP": "Handshake",
            "MonitorAgentVer": "VL20151102.01",
            "Result": "PASS",
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        return self.backend.HTTPPost(inputstr)

    def FATStart(self, data):
        station = "SWDLTEST"
        step = "request"
        inputstr_dict = {
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "FixtureID": data["factory.wl_mac_request"],
            "MBSN": "NOMBSN",
            # "ClientInfo": ClientInfoIP,
            "Step": step,
            "Station": station,
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        logging.info("FATStart: %s", data)
        return self.backend.HTTPPost(data)

    def FATEnd(self, data):
        station = "FAT"
        step = "request"
        inputstr_dict = {
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "SN": data["serials.serial_number"],
            "MBSN": data["serials.mlb_serial_number"],
            "ClientInfo": "10.18.6.41",
            "Station": station,
            "Step": step,
            "ErrCode": "PASS",
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        logging.info("FATEnd: %s", data)
        return self.backend.HTTPPost(data)

    def FATLightD1(self, data):
        station = "RUNIN"
        step = "RUNIN"
        inputstr_dict = {
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "ClientInfo": "10.18.6.41",
            "STATION": station,
            "Serial_Number": data["serials.serial_number"],
            "STEP": "D1",
            "NEXTSTEP": "FAT",
            "INTERVAL": "1200",
            "ERRORCODE": "Y",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        logging.info("FATLightD1: %s", data)
        return self.backend.HTTPPost(data)

    def FATLightFAT(self, data):
        station = "RUNIN"
        step = "RUNIN"
        inputstr_dict = {
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "ClientInfo": "10.18.6.41",
            "STATION": station,
            "Serial_Number": data["serials.serial_number"],
            "STEP": "FAT",
            "NEXTSTEP": "ChromeRunInPass",
            "INTERVAL": "10800",
            "ERRORCODE": "Y",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        logging.info("FATLightFAT: %s", data)
        return self.backend.HTTPPost(data)

    def RunInLightCRP(self, data):
        station = "RUNIN"
        step = "RUNIN"
        inputstr_dict = {
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "ClientInfo": "10.18.6.41",
            "STATION": station,
            "Serial_Number": data["serials.serial_number"],
            "STEP": "ChromeRunInPass",
            "NEXTSTEP": "DTPass",
            "INTERVAL": "108000",
            "ERRORCODE": "G",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        logging.info("RunInLightCRP: %s", data)
        return self.backend.HTTPPost(data)

    def OverTwoDays(self, data):
        station = "RUNIN"
        step = "RUNIN"
        inputstr_dict = {
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "ClientInfo": "10.18.6.41",
            "STATION": station,
            "Serial_Number": data["serials.serial_number"],
            "STEP": "ChromeRunInPass",
            "NEXTSTEP": "DTPass",
            "INTERVAL": "108000",
            "ERRORCODE": "P",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        logging.info("OwerTwoDays: %s", data)
        return self.backend.HTTPPost(data)

    def DTLight(self, data):
        station = "RUNIN"
        step = "RUNIN"
        inputstr_dict = {
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "ClientInfo": "10.18.6.41",
            "STATION": station,
            "Serial_Number": data["serials.serial_number"],
            "STEP": "DTLight",
            "NEXTSTEP": "Finalize",
            "INTERVAL": "1200",
            "ERRORCODE": "Y",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        logging.info("DTLight: %s", data)
        return self.backend.HTTPPost(data)

    def CheckDUTStatus(self, data):
        station = "RUNIN"
        step = "RUNIN"
        inputstr_dict = {
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "ClientInfo": "10.18.6.41",
            "STATION": station,
            "Serial_Number": data["serials.serial_number"],
            "STEP": "TestFail",
            "NEXTSTEP": "FAT",
            "INTERVAL": "1200",
            "ERRORCODE": "R",
            "DL_SWITCHIP": data["factory.switchip"],
            "DL_PORT": data["factory.switchport"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr_dict)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        return self.backend.HTTPPost(data)

    def FFTStart(self, data):
        return self.DUMMY(data, "DUMMY")

    def FFTEnd(self, data):
        return self.DUMMY(data, "DUMMY")

    def RUNINStart(self, data):
        return self.DUMMY(data, "DUMMY")

    def RUNINEnd(self, data):
        station = "CRP"
        step = "Request"
        inputstr = {
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "SN": data["serials.serial_number"],
            "MBSN": data["serials.mlb_serial_number"],
            "ClientInfo": "10.18.6.41",
            "Station": station,
            "Step": step,
            "ErrCode": "PASS",
        }
        inputstr = self.backend.ConvertToInputStr(inputstr)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        return self.backend.HTTPPost(data)

    def GRTStart(self, data):
        data['factory.WLANID'] = data['factory.WLANID'].strip('droid')
        data['factory.BT_MAC'] = data['factory.BT_MAC'].strip('droid')
        station = "SWDL1"
        step = "Handshake"
        inputstr = {
            "Station": station,
            "Step": step,
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "WLANID": data["factory.WLANID"],
            "BT_MAC": data["factory.BT_MAC"],
            #"EC_VER": data["factory.EC_VER"],
            #"CR50_RO_VER": data["factory.CR50_RO_VER"],
            #"CR50_RW_VER": data["factory.CR50_RW_VER"],
            #"Google_Name": data["factory.Google_Name"],
            #"Release_Image_Version": data["factory.Release_Image_Version"],
            #"Test_Image_Version": data["factory.Test_Image_Version"],
            "MBSN": data["serials.mlb_serial_number"],
            "BIOS": data["factory.BIOS"],
            "HWID": data["hwid"],
            "MACID": "NOMAC",
            "ERRCode": "PASS",
            "CollectMACFlag": "Y",
            "Serial_Number": data["serials.serial_number"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        return self.backend.HTTPPost(data)

    def GRTEnd(self, data):
        station = "FRT"
        step = "Request"
        inputstr = {
            "STATION": station,
            "STEP": step,
            "ERRCode": "PASS",
            "MonitorAgentVer": "WEBAPI2.0.0.1",
            "MBSN": data["serials.mlb_serial_number"],
            "MACID": "NOMAC",
            "SN": data["serials.serial_number"],
        }
        inputstr = self.backend.ConvertToInputStr(inputstr)
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        return self.backend.HTTPPost(data)

    def Finalized(self, data):
        logging.info("Debug1: data is %s", data)
        station = "SWDL"
        step = "Handshake"
        inputstr = {
            "STATION": station,
            "STEP": step,
            "WLANID": data["wlanid"],
            "BT_MAC": data["bt_mac"],
            "ERRCode": "PASS",
            "Serial_Number": data["serial_number"],
            "MBSN": data["mlb_serial_number"],
            "MAC": "NOMAC",
            "BIOS": data["bios"],
            "MonitorAgenVer": "WEBAPI2.0.0.1",
            "HWID": data["hwid"],
        }
        logging.info("Debug1: input str is %s", inputstr)
        inputstr = self.backend.ConvertToInputStr(inputstr)
        logging.info("Debug2: input str is %s", inputstr)
        p = {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        logging.info("Debug3: Stage finalize request: %s", p)

        station_light = "RUNIN"
        step_light = "RUNIN"
        inputstr_light = {
            "STATION": station_light,
            "STEP": "Finalized",
            "ERRORCODE": "G",
            "DL_SWITCHIP": data["dl_switchip"],
            "DL_PORT": data["dl_switchport"],
            "Serial_Number": data["serial_number"],
            "MonitorAgenVer": "WEBAPI2.0.0.1",
        }
        inputstr_light = self.backend.ConvertToInputStr(inputstr_light)
        p_light = {"BU": self.bu, "Station": station_light, "Step": step_light, "Inputstr": inputstr_light}
        return self.backend.HTTPPost(p), self.backend.HTTPPost(p_light)

    def FinalizedFQC(self, data):
        station = "QRT"
        step = "Handshake"
        inputstr = {
            "STATION": station,
            "STEP": step,
            "ERRCode": "PASS",
            "MonitorAgenVer": "WEBAPI2.0.0.1",
            "Serial_Number": data["serial_number"],
        }
        data.update(
            {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        )
        inputstr = self.backend.ConvertToInputStr(inputstr)
        p = {"BU": self.bu, "Station": station, "Step": step, "Inputstr": inputstr}
        logging.info("CheckDUTStatus: %s", data)
        return self.backend.HTTPPost(p)

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
            "FAT": self.middleware.FATStart,
            "FATLightD1": self.middleware.FATLightD1,
            "FATLightFAT": self.middleware.FATLightFAT,
            "FFT": self.middleware.FFTStart,
            "RUNINLightCRP": self.middleware.RunInLightCRP,
            "Over2Days": self.middleware.OverTwoDays,
            "DTLight": self.middleware.DTLight,
            "SendRedLight": self.middleware.CheckDUTStatus,
            "GRT": self.middleware.GRTStart,
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
            "Refinalize": self.middleware.FinalizedFQC,
        }
        return self._Dispatch(data, event, event_mapping)

    def GetDeviceInfo(self, data):
        """Returns information about the device's expected configuration.

        Args:
          data: A FactoryDeviceData instance.

        Returns:
          A mapping in DeviceData format.
        """
        logging.info("DUT %s requesting device information", data)
        return self.middleware.FATStart(data)

    def ActivateRegCode(self, ubind_attribute, gbind_attribute, hwid):
        """Notifies shopfloor backend that DUT has deployed a registration code.

        Args:
          ubind_attribute: A string for user registration code.
          gbind_attribute: A string for group registration code.
          hwid: A string for the HWID of the device.

        Returns:
          A mapping in DeviceData format.
        """
        logging.info(
            "DUT <hwid=%s> requesting to activate regcode(u=%s,g=%s)",
            hwid,
            ubind_attribute,
            gbind_attribute,
        )
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
        return {}


class ThreadedXMLRPCServer(
    socketserver.ThreadingMixIn, xmlrpc.server.SimpleXMLRPCServer
):
    """A threaded XML RPC Server."""


def RunAsServer(address, port, instance, logRequest=False):
    """Starts an XML-RPC server in given address and port.

    Args:
      address: Address to bind server.
      port: Port for server to listen.
      instance: Server instance for incoming XML RPC requests.
      logRequests: Boolean to indicate if we should log requests.

    Returns:
      Never returns if the server is started successfully, otherwise some
      exception will be raised.
    """
    server = ThreadedXMLRPCServer(
        (address, port), allow_none=True, logRequests=logRequest
    )
    server.register_introspection_functions()
    server.register_instance(instance)
    logging.info(
        'Server started: http://%s:%s "%s" version %s',
        address,
        port,
        instance.__class__.__name__,
        instance.GetVersion(),
    )
    server.serve_forever()


def main():
    """Main entry when being invoked by command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-a",
        "--address",
        metavar="ADDR",
        default=DEFAULT_SERVER_ADDRESS,
        help="address to bind (default: {0})".format(DEFAULT_SERVER_ADDRESS),
    )
    parser.add_argument(
        "-p",
        "--port",
        metavar="PORT",
        type=int,
        default=DEFAULT_SERVER_PORT,
        help="port to bind (default: {0})".format(DEFAULT_SERVER_PORT),
    )
    parser.add_argument(
        "-l",
        "--legacy",
        default=False,
        action="store_true",
        help="use legacy MsdbDatabaseShopfloorBackend.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        default=False,
        action="store_true",
        help="provide verbose logs for debugging.",
    )
    args = parser.parse_args()

    log_format = "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format=log_format
    )

    # Disable all DNS lookups, since otherwise the logging code may try to
    # resolve IP addresses, which may delay request handling.
    socket.getfqdn = lambda name: name or "localhost"

    try:
        RunAsServer(
            address=args.address,
            port=args.port,
            instance=ShopfloorService(),
            logRequest=args.verbose,
        )
    finally:
        logging.warning("Server stopped.")


if __name__ == "__main__":
    main()
