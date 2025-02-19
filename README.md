# Shopfloor Integration

## 使用 Git 对 Shopfloor Service 进行统一管理

**关于 Shopfloor Service 更改，请先行在本地 Git 仓库更改, 更改完成后 Create MR, 审核通过后会自动部署至生产服务器.**

**最新的 DOME factory server docker image 版本为： factory-server-20190916140050-72994a-docker-1.10.3.txz.**

## 版本说明

所有开发及稳定版本都在 `src` 目录中，请勿使用 `unsupported` 中任何内容，

版本说明如下, 当前推荐使用版本 `v2.0.10`:

注: **`stable > rc > beta > alpha`**, 请优先选择 `stable version`.

| Version Branch | Description                                         | Status                          |
| -------------- | --------------------------------------------------- | ------------------------------- |
| v1.0.B         | Default Version, for `SEL` process                  | Deprecated                      |
| v1.1.B         | `STN` text process                                  | Deprecated                      |
| v1.2.B         | `STN` SMT text + FA DB process                      | End Support Date (2020/06/01)   |
| v1.3.B         | `v1.3.B` include `text` and `Database` full station | Deprecated                      |
| v1.4.B         | `v1.4.B` only for `Database` process                | Deprecated                      |
| v1.5.B         | For `QSMC BU3`                                      | Stop Maintenance                |
| v2.0.B         | `STN` full Database version (SMT DB + FA DB)        | Long Time Support (Recommended) |
| v3.0.B         | Develop version, prepare support Python3            | Developing                      |

## Station description

### QCMC BU4 Factory SW Station

| Stage | Items     | Station      | 接口类型  |
| ----- | --------- | ------------ | --------- |
| SMT   | Start_SMT | FVS          | Samba     |
|       | End_SMT   | FVS_PASS     | Samba     |
| FA    | Start_FAT | SWDLTEST/D1  | Request   |
|       | End_FAT   | FAT/SWDL1/20 | Request   |
|       | Start_GRT | FRT/DT       | Handshake |
|       | End_GRT   | FRT/25       | Request   |
|       | Wipe      | SWDL/45      | Handshake |
|       | QA_Reset  | QRT          | Handshake |

### QSMC BU3 Factory SW Station

| Stage | Items     | Station     | 接口类型  |
| ----- | --------- | ----------- | --------- |
| SMT   | Start_SMT | FVS         | Samba     |
|       | End_SMT   | FVS_PASS    | Samba     |
| FA    | Start_FAT | SWDLTEST/D1 | Request   |
|       | End_FAT   | SWDLTest/20 | Handshake |
|       | End_FFT   | FFT/30      | Request   |
|       | End_RunIn | FRT/25      | Request   |
|       | End_GRT   | SWDL/40     | Request   |
|       | Wipe      | SWDL/45     | Handshake |

## BU4 STN Database 服务器接口

### Default Setting Information

```python
DEFAULT_SERVER_PORT = 6666
DEFAULT_SERVER_ADDRESS = '0.0.0.0'
DEFAULT_ROOT_DIR = '/opt/sdt'
DEFAULT_TIMEOUT_SECS = 10
```

### FA MSDB Information

```python
DEFAULT_MSDB_HOST = '10.18.6.41'
DEFAULT_MSDB_USER = 'SDT'
DEFAULT_MSDB_PASSWORD = 'SDT#7'
DEFAULT_MSDB_DATABASE = 'QMS'
DEFAULT_MSDB_SP = 'MonitorPortal'
DEFAULT_MSDB_BU = 'NB4'
```

### FA Backup MSDB Information

```python
BACKUP_MSDB_HOST = '10.18.6.42'
TESTED_MSDB_BU = 'NB4TEST'
```

### SMT MSDB Information

**Note: SMT_MSDB_SP = 'MonitorFVSRequest' not supported, used DEFAULT_MSDB_SP.**

```python
SMT_MSDB_HOST = '10.18.8.11'
SMT_MSDB_USER = 'MunSFUser'
SMT_MSDB_PASSWORD = 'is6<2g'
SMT_MSDB_DATABASE = 'SMT'
SMT_MSDB_SP = 'MonitorFVSRequest'
SMT_MSDB_BU = 'NB4'
```
