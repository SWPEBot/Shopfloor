#!/usr/bin/env python2
#
# Copyright 2019 The Quanta Computer Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
#
# Base on Chromium OS factory shopfloor service API 1.0.
#
# Release Date: Thu July 20 2020 8:49:47 AM
"""Implementation of ChromeOS Factory Shopfloor Service, version 2.3.1"""

import os
import re
import csv
import time
import socket
import logging
import optparse
import binascii
import SocketServer
import SimpleXMLRPCServer
from pymssql import connect


# Define shopfloor service config
DEFAULT_SERVER_PORT = 11130
DEFAULT_SERVER_ADDRESS = '0.0.0.0'
#Max times of each ip in Host_Server_IP_FA need try to connect 
MAX_RETRIES_TIMES=3
#when dut connect fail, we need delay a few seconds ,then do next connect
DELAY_SEC=3

# The setting of server parameter
DataBase_Port = 'NB4'
DataBase_SP = 'MonitorPortal'
DataBase_Group = ['SMT', 'QMS']
Login_User = ['SDT', 'MunSFUser']
Login_Password = ['SDT#7', 'is6<2g']
#The IP group of Batch_Server_FA
Host_Server_IP_FA = ['10.18.6.42',
                     '10.18.6.41',
                     '10.18.6.50',
                     '40.30.1.5',
                     '40.30.1.4',
                     '40.30.1.6',
                     '40.31.1.4',
                     '40.31.1.5',
                     '40.31.1.6',
                     '40.32.1.4',
                     '40.32.1.5',
                     '40.32.1.6',
                     '40.33.1.4',
                     '40.33.1.5',
                     '40.33.1.6']
#IP Batch server for SMT
Host_Server_IP_SMT = ['10.18.8.11']
#Host_Server_IP = ['10.18.6.42', '10.18.6.41', '10.18.6.50', '10.18.8.11']#The IP group of Batch_Server[20200617]
"""Path for registration code csv file Example."""

class QuantaShopfloorError(Exception):
  """A wrapper for exceptions from Quanta shopfloor backends."""
  pass

class NewlineTerminatedCSVDialect(csv.excel):
  lineterminator = '\n'

class QuantaSharedDriveShopfloorBackend(object):
  """Quanta Shopfloor Backend.
  This implementation is based on mssql server.
  Attributes:
    timeout_secs: Integer for timeout of one request.
    initial_poll_secs: Integer for delay of initial check after request sent.
    result_key_names: A list of key names in response for result.
  """
  Error = QuantaShopfloorError

  def __init__(self, timeout_secs=10, initial_poll_secs=0.1,
               result_key_names=None):
    """Constructor."""
    self.timeout_secs = timeout_secs
    self.initial_poll_secs = initial_poll_secs
    if result_key_names is None:
      # The key name SF_CFG_CHK is FA Request, RESULT for FA Handshake,
      # CheckResult for SMT Request, Result for SMT Handshake.
      # SMT QMS set an extra error space key for the function.
      result_key_names = ['RESULT', 'SF_CFG_CHK', 'CheckResult', ' Result']
    self.result_key_names = result_key_names

  @staticmethod
  def FormatKeyValuePairs(args):
    """Formats key/value pairs for a request file.
    Args:
      args: A tuple of key/value pairs, e.g., (('A', 'B'), ('C', 'D')),
      e.g., {'A': 'B', 'C': 'D'}.  Values are coerced to strings;
      None represents an empty string.
    Returns:
      A string like'A=B;$;C=D;$;', e.g. "SET MB_NUM=123;$;SET RESULT=PASS"
    """
    if isinstance(args, dict):
      args = sorted(args.items())
    return ''.join(
        '%s=%s;$;' % (k, "" if v is None else str(v)) for k, v in args)

  @staticmethod
  def ParseKeyValuePairs(data):
    """Parses key/value pairs from a response file.
    Invalid lines are logged and ignored.
    Args:
      data: An input string, e.g., 'A=B;$;C=D;$;'
    Returns:
      A dictionary, e.g., {'A': 'B', 'C': 'D'}
    """
    ret = {}
    for line in filter(None, data.split(';$;')):
      line = line.rstrip('\n')
      if not line:
        continue
      line = re.sub(r'(?i)^set ', '', line)
      key, equals, value = line.partition('=')
      if equals:
        ret[key] = value
      else:
        logging.error('Invalid line %r', line)
    return ret

  @staticmethod
  def FormatTime():
    """Formats the current time for use by the backend."""
    return time.strftime('%Y%m%d%H%M%S', time.localtime())

  def CheckResponse(self, response):
    """Checks if a response indicated pass or failed.
    Args:
      response: A dictionary from raw Quanta shopfloor key-value pair.
    """
    err_msg = response.get('ErrMsg') or response.get('ERR_MSG')
    if err_msg and err_msg != 'OK':
      raise self.Error('Error %r in response' % err_msg)
    result_keys = [response.get(key) for key in self.result_key_names]
    result = [string for string in result_keys if string is not None]
    logging.info('The result keys is %s, result is %s', result_keys, result)
    if not any('PASS' or 'OK' in string for string in result):
      raise self.Error('Expected Pass or OK in response, but got %r ' % result)
    for string in result:
      if "not exist" in string:
         raise self.Error("MB serial number not exist")
    return True

  def Call(self, request):
    """Sends a request to backend and returns response.
    Args:
      request: A dictionary with request context.
    Raises:
      QuantaShopfloorError if response cannot be fetched or if response has
      indicated error (via CheckResponse).
    """
    #print("Current station is %s " % request["STATION"])
    data = self.FormatKeyValuePairs(request)
    # for Retry in range(0,9):#Retry 3 times with each IP[41,42,45]
    if request['STATION'] == 'FVS':
      try:
        conn = connect(host=Host_Server_IP_SMT[0],
                       user=Login_User[1],
                       password=Login_Password[1],
                       database=DataBase_Group[0],
                       login_timeout=300)
      except Exception as e:
        logging.info('DEBUG: Connect MS Database Error: %s', e)
        time.sleep(3)
        return None
    else:
      for Retry in range(0, len(Host_Server_IP_FA)*MAX_RETRIES_TIMES):
        try:
          print("try to connect %s %d time" % (Host_Server_IP_FA[Retry/MAX_RETRIES_TIMES], (Retry%MAX_RETRIES_TIMES+1)))
          conn = connect(host=Host_Server_IP_FA[Retry/MAX_RETRIES_TIMES],
                         user=Login_User[0],
                         password=Login_Password[0],
                         database=DataBase_Group[1],
                         login_timeout=30)
          break
        except Exception as e:
          logging.info('DEBUG: Connect MS Database Error: %s', e)
          time.sleep(DELAY_SEC)
      print("Connected %s" % Host_Server_IP_FA[Retry/MAX_RETRIES_TIMES])
    sql = '''
   DECLARE @ReturnValue varchar(8000)
   EXEC %s '%s', '%s', '%s', '%s', @ReturnValue output
   SELECT @ReturnValue ''' % (DataBase_SP, DataBase_Port, request['STATION'],
                              request['MSDB_STEP'], data)
    try:
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
      data = ''.join(str(data[0]))
      logging.info('DEBUG_Call: Shopfloor Response Message is "%s"', data)
    except Exception as e:
      conn.close()
      logging.info('DEBUG_Call: Operate Exception: "%s"', e)
      conn = None
      # continue
    conn.close()  #Release the Server-resource after data interaction
    response = self.ParseKeyValuePairs(data)
    if len(response) == 0:
      return
    else:
      self.CheckResponse(response)
    return response

class QuantaShopfloor(object):
  """Implementation of shopfloor for Quanta Chrome project."""
  # Key names in factory device data.
  KEY_SERIAL_NUMBER = 'serials.serial_number'
  KEY_MLB_SERIAL_NUMBER = 'serials.mlb_serial_number'
  KEY_HWID = 'hwid'
  def __init__(self):
    self.backend = QuantaSharedDriveShopfloorBackend()
    self.translate_response = {
        'QCI_Model': 'factory.Quanta_Project_Name',
        'Work_Order': 'factory.Work_Order',
        'HWID': self.KEY_HWID,
        'MB_NUM': self.KEY_MLB_SERIAL_NUMBER,
        'User_code': 'vpd.rw.ubind_attribute',
        'Group_code': 'vpd.rw.gbind_attribute',
        'Region_Code': 'vpd.ro.region',
        'SN': self.KEY_SERIAL_NUMBER,
        'LCD': 'component.lcd_type',
        'chrome_lcd_pid': 'component.chrome_lcd_pid',
        'gbu_type': 'component.cpu_model',
        'SparePart': 'component.is_spare_part',
        'ALL_RAM_SIZE': 'component.memory_size',
        'sec_hdd': 'component.nvme_storage_size',
        'eMMcHDD_Szie': 'component.storage_size',
        'VendorID': 'component.dram_part_num',
        'LINE': 'factory.line',
        'SKUID': 'component.sku'
    }
    self.translate_request = {v: k for k, v in
                              self.translate_response.iteritems()}

  @staticmethod
  def GenerateRequestID():
    """Generates a random 8-character hex string to use as a request ID."""
    return binascii.hexlify(os.urandom(4))

  def CallBackend(self, request):
    """Calls a shard drive based shopfloor backend.

    Args:
      request: A translated key-value pair.
    """
    return self.TranslateResponse(self.backend.Call(request))

  def TranslateSparePart(self, data):
    """For SMT Translate Spare Part Process."""
    key_is_sp = 'component.is_spare_part'
    value_is_sp = data.get(key_is_sp, '')
    if value_is_sp == 'Y':
      data[key_is_sp] = True
    else:
      data[key_is_sp] = False
    return data

  def TranslateRequest(self, data, extra_data=None):
    """Converts a factory device data to request for backend.
    Args:
      data: A factory device data object.
      extra_data: A mapping for extra values to write into request.
    Returns:
      A key-value pair request.
    """
    request = {self.translate_request[k]: v for k, v in data.iteritems()
               if k in self.translate_request}
    request['Date'] = self.backend.FormatTime()
    if extra_data:
      request.update(extra_data)
    logging.info('Shopfloor Request Message is %s', request)
    return request

  def TranslateResponse(self, response):
    """Converts a shopfloor backend response to factory device data.
    Args:
      response: A shopfloor backend response mapping.
    Returns:
      A factory device data mapping.
    """
    data = {self.translate_response[k]: v for k, v in response.iteritems()
            if k in self.translate_response}
    # For SMT Translate Spare Part Data
    if 'component.is_spare_part' in data:
      data = self.TranslateSparePart(data)
    return data

  def SMT_START(self, data):
    extra_data = {'STATION': 'FVS',
                  'MSDB_STEP': 'Request',
                  'MonitorAgentVer': 'VL20151102.01'}
    request = self.TranslateRequest(data, extra_data)
    return self.CallBackend(request)

  def SMT_END(self, data):
    extra_data = {'STATION': 'FVS',
                  'onboard_wifi': 'false',
                  'WLANID': data['factory.wifi_mac'],
                  'BT_MAC': data['factory.bluetooth_mac'],
                  'MSDB_STEP': 'Handshake',
                  'MonitorAgentVer': 'VL20151102.01',
                  'Result': 'PASS'}
    request = self.TranslateRequest(data, extra_data)
    return self.CallBackend(request)

  def FAT_START(self, data):
    extra_data = {'STATION': 'SWDLTEST',
                  'MSDB_STEP': 'Request',
                 #'SN': data['serials.serial_number'],
                  'FixtureID': data['factory.wl_mac_request'],
                  'MBSN': 'NOMBSN',
                  'MonitorAgentVer': 'VL20151102.01'}
    request = self.TranslateRequest(data, extra_data)
    return self.CallBackend(request)

  # For Send the Yellow Light, It marks the DUT enter the OS and Pass the D1 Station
  def FAT_Light_D1(self, data):
      extra_data = {'STATION': 'RUNIN',
                    'MSDB_STEP': 'RUNIN',
                    'Serial_Number': data['serials.serial_number'],
                    'STEP': 'D1',
                    'NEXTSTEP': 'FAT',
                    'INTERVAL': '1200',
                    'ERRORCODE': 'Y',
                    'DL_SWITCHIP': data['factory.switchip'],
                    'DL_PORT': data['factory.switchport'],
                    'MonitorAgentVer': 'VL20151102.01'}
      request = self.TranslateRequest(
          data, extra_data)
      return self.CallBackend(request)

  # For Send the White Light, It marks the DUT Pass the FAT Station and Start RunIn
  def FAT_Light_FAT(self, data):
      extra_data = {'STATION': 'RUNIN',
                    'MSDB_STEP': 'RUNIN',
                    'Serial_Number': data['serials.serial_number'],
                    'STEP': 'FAT',
                    'NEXTSTEP': 'ChromeRunInPass',
                    'INTERVAL': '10800',
                    'ERRORCODE': 'W',
                    'DL_SWITCHIP': data['factory.switchip'],
                    'DL_PORT': data['factory.switchport'],
                    'MonitorAgentVer': 'VL20151102.01'}
      request = self.TranslateRequest(
          data, extra_data)
      return self.CallBackend(request)

  # For Send the Pink Light, It marks the DUT RunIn Passed
  def RunIn_Light_CRP(self, data):
      extra_data = {'STATION': 'RUNIN',
                    'MSDB_STEP': 'RUNIN',
                    'Serial_Number': data['serials.serial_number'],
                    'STEP': 'ChromeRunInPass',
                    'NEXTSTEP': 'DTPass',
                    'INTERVAL': '108000',
                    'ERRORCODE': 'P',
                    'DL_SWITCHIP': data['factory.switchip'],
                    'DL_PORT': data['factory.switchport'],
                    'MonitorAgentVer': 'VL20151102.01'}
      request = self.TranslateRequest(
          data, extra_data)
      return self.CallBackend(request)

  # For Send the Cyan Light, It marks the DUT DT Passed
  def DT_Light(self, data):
      extra_data = {'STATION': 'RUNIN',
                    'MSDB_STEP': 'RUNIN',
                    'Serial_Number': data['serials.serial_number'],
                    'STEP': 'DTPass',
                    'NEXTSTEP': 'Finalize',
                    'INTERVAL': '1800',
                    'ERRORCODE': 'C',
                    'DL_SWITCHIP': data['factory.switchip'],
                    'DL_PORT': data['factory.switchport'],
                    'MonitorAgentVer': 'VL20151102.01'}
      request = self.TranslateRequest(
          data, extra_data)
      return self.CallBackend(request)

  # For Send the Green Light, It marks Finalize Passed
  def FinalizePassLight(self, data):
      extra_data = {'STATION': 'RUNIN',
                    'MSDB_STEP': 'RUNIN',
                    'Serial_Number': data['serial_number'],
                    'STEP': 'Finalize',
                    'ERRORCODE': 'G',
                    'DL_SWITCHIP': data['factory.switchip'],
                    'DL_PORT': data['factory.switchport'],
                    'MonitorAgentVer': 'VL20151102.01'}
      request = self.TranslateRequest(
          data, extra_data)
      return self.CallBackend(request)

  # For Send the Red Light, It marks there is something wrong on DUT
  def CheckDUTStatus(self, data):
      extra_data = {'STATION': 'RUNIN',
                    'MSDB_STEP': 'RUNIN',
                    'Serial_Number': data['serials.serial_number'],
                    'ERRORCODE': 'R',
                    'DL_SWITCHIP': data['factory.switchip'],
                    'DL_PORT': data['factory.switchport'],
                    'MonitorAgentVer': 'VL20151102.01'}
      request = self.TranslateRequest(
          data, extra_data)
      return self.CallBackend(request)

  def FAT_END(self, data):
    """Helin Marked, QMS Need ErrorCode Check Routing Status."""
    extra_data = {'STATION': 'FAT',
                  'MSDB_STEP': 'Request',
                  'ERRCode': 'PASS',
                  'SN': data['serials.serial_number'],
                  'MBSN': data['serials.mlb_serial_number'],
                  'MonitorAgentVer': 'VL20151102.01'}
    request = self.TranslateRequest(data, extra_data)
    return self.CallBackend(request)

  def FFT_START(self, data):
    return self.DUMMY(data, 'DUMMY')

  def FFT_END(self, data):
    return self.DUMMY(data, 'DUMMY')

  def RUNIN_START(self, data):
    return self.DUMMY(data, 'DUMMY')

  def RUNIN_END(self, data):
    extra_data = {'STATION': 'CRP',
                  'MSDB_STEP': 'Request',
                  'ERRCode': 'PASS',
                  'SN': data['serials.serial_number'],
                  'MBSN': data['serials.mlb_serial_number'],
                  'MonitorAgentVer': 'VL20151102.01'}
    request = self.TranslateRequest(data, extra_data)
    return self.CallBackend(request)
   #return self.DUMMY(data, 'DUMMY')

  def GRT_START(self, data):
    extra_data = {'STATION': 'SWDL1',
                  'MSDB_STEP': 'Handshake',
                  'WLANID': data['factory.wifi_mac'],
                  'BT_MAC': data['factory.bluetooth_mac'],
                  'MBSN': data['serials.mlb_serial_number'],
                  'BIOS': data['factory.fwid'],
                  'MACID': 'NOMAC',
                  'ERRCode': 'PASS',
                  'MonitorAgentVer': 'VL20151102.01',
                  'Serial_Number': data['serials.serial_number']}
    request = self.TranslateRequest(data, extra_data)
    return self.CallBackend(request)

  def GRT_END(self, data):
    extra_data = {'STATION': 'FRT',
                  'MSDB_STEP': 'Request',
                  'SN': data['serials.serial_number'],
                  'ERRCode': 'PASS',
                  'MonitorAgentVer': 'VL20151102.01'}
    request = self.TranslateRequest(data, extra_data)
    return self.CallBackend(request)

  def FINALIZED(self, data):
    extra_data = {'STATION': 'SWDL',
                  'MSDB_STEP': 'Handshake',
                  'ERRCode': 'PASS',
                  'HWID': data['hwid'],
                  'Serial_Number': data['serial_number'],
                  'MBSN': data['mlb_serial_number'],
                  'WLANID': data['wlanid'],
                  'BT_MAC': data['bt_mac'],
                  'MAC': 'NOMAC',
                  'BIOS': data['bios'],
                  'MonitorAgenVer': 'VL20151102.01'}
    request = self.TranslateRequest(data, extra_data)

    extra_data_light = {'STATION': 'RUNIN',
                  'MSDB_STEP': 'RUNIN',
                  'Serial_Number': data['serial_number'],
                  'STEP': 'Finalize',
                  'ERRORCODE': 'G',
                  'DL_SWITCHIP': data['dl_switchip'],
                  'DL_PORT': data['dl_switchport'],
                  'MonitorAgentVer': 'VL20151102.01'}
    request_light = self.TranslateRequest(
        data, extra_data_light)

    return (self.CallBackend(request), self.CallBackend(request_light)) # Finalize Passed and send green light

  def FINALIZED_FQC(self, data):
    extra_data = {'STATION': 'QRT',
                  'MSDB_STEP': 'Handshake',
                  'ERRCode': 'PASS',
                  'Serial_Number': data['serial_number'],
                  'MonitorAgenVer': 'VL20151102.01'}
    request = self.TranslateRequest(data, extra_data)
    return self.CallBackend(request)

  def DUMMY(self, *args, **kargs):
    logging.info('Dummy API invoked %r %r.', args, kargs)
    return {}


class ShopfloorService(object):
  def __init__(self):
    self.backend = QuantaShopfloor()

  def GetVersion(self):
    """Returns the version of supported protocol."""
    return '2.3.1'

  @staticmethod
  def _Dispatch(data, key, mapping):
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
    return self._Dispatch(data, station, {
        'SMT': self.backend.SMT_START,
        'FAT': self.backend.FAT_START,
        'FATLightD1': self.backend.FAT_Light_D1,  # Yellow Light, Enter OS and D1 Passed
        'FATLightFAT': self.backend.FAT_Light_FAT, # White Light, FAT Passed
        'FFT': self.backend.FFT_START,
        'RUNINLightCRP': self.backend.RunIn_Light_CRP,  # Pink Light, RunIn Passed
        'DTLight': self.backend.DT_Light,  # Cyan Light, It marks DT Station Passed
        'SendRedLight': self.backend.CheckDUTStatus, # Red Light
        'GRT': self.backend.GRT_START
    })

  def NotifyEnd(self, data, station):
    """Notifies shopfloor backend that DUT has finished a manufacturing station.
    Args:
      data: A FactoryDeviceData instance.
      station: A string to indicate manufacturing station.
    Returns:
      A mapping in DeviceData format.
    """
    return self._Dispatch(data, station, {
        'SMT': self.backend.SMT_END,
        'FAT': self.backend.FAT_END,
        'FFT': self.backend.FFT_END,
        'RUNIN': self.backend.RUNIN_END,
        'GRT': self.backend.GRT_END
    })

  def NotifyEvent(self, data, event):
    """Notifies shopfloor backend that the DUT has performed an event.
    Args:
      data: A FactoryDeviceData instance.
      event: A string to indicate manufacturing event.
    Returns:
      A mapping in FactoryDeviceData format.
    """
    assert event in ['Finalize', 'Refinalize']
    logging.info('DUT sending event %s', event)
    return self._Dispatch(data, event, {
        'Finalize': self.backend.FINALIZED,
        'Refinalize': self.backend.FINALIZED_FQC
    })

  def GetDeviceInfo(self, data):
    """Returns information about the device's expected configuration.

    Args:
      data: A FactoryDeviceData instance.

    Returns:
      A mapping in DeviceData format.
    """
    logging.info('DUT %s requesting device information', data)
    return self.backend.FAT_START(data)

  def ActivateRegCode(self, ubind_attribute, gbind_attribute, hwid):
    """Notifies shopfloor backend that DUT has deployed a registration code.

    Args:
      ubind_attribute: A string for user registration code.
      gbind_attribute: A string for group registration code.
      hwid: A string for the HWID of the device.

    Returns:
      A mapping in DeviceData format.
    """
    logging.info('DUT <hwid=%s> requesting to activate regcode(u=%s,g=%s)',
                 hwid, ubind_attribute, gbind_attribute)
    if hwid == [None,'NA']:  #for smt spare part
      board = 'TOMATO'
    else:
      board = hwid.partition(' ')[0]

    with open(REGCODE_LOG_CSV, 'ab') as f:
      csv.writer(f, dialect=NewlineTerminatedCSVDialect).writerow(
          [board, ubind_attribute, gbind_attribute,
           time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()), hwid])
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
    logging.info('DUT %s updating test results for <%s> with status <%s> %s',
                 data.get('serials.serial_number'), test_id, status,
                 details.get('error_message') if details else '')
    return {}


class ThreadedXMLRPCServer(SocketServer.ThreadingMixIn,
                           SimpleXMLRPCServer.SimpleXMLRPCServer):
  """A threaded XML RPC Server."""
  pass


def RunAsServer(address, port, instance, logRequest=False):
  """Starts a XML-RPC server in given address and port.

  Args:
    address: Address to bind server.
    port: Port for server to listen.
    instance: Server instance for incoming XML RPC requests.
    logRequests: Boolean to indicate if we should log requests.

  Returns:
    Never returns if the server is started successfully, otherwise some
    exception will be raised.
  """
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
  socket.getfqdn = lambda name: name or 'localhost'

  try:
    RunAsServer(address=options.address, port=options.port,
                instance=ShopfloorService(),
                logRequest=options.verbose)
  finally:
    logging.warn('Server stopped.')

if __name__ == '__main__':
  main()
