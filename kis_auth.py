# -*- coding: utf-8 -*-
# ====|  (REST) 접근 토큰 / (Websocket) 웹소켓 접속키 발급 에 필요한 API 호출 샘플 아래 참고하시기 바랍니다.  |=====================
# ====|  API 호출 공통 함수 포함                                  |=====================

import asyncio
import copy
import json
import logging
import os
import time
from base64 import b64decode
from collections import namedtuple
from collections.abc import Callable
from datetime import datetime
from io import StringIO
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import pandas as pd

# pip install requests (패키지설치)
import requests

# 웹 소켓 모듈을 선언한다.
import websockets

# pip install PyYAML (패키지설치)
import yaml
from Crypto.Cipher import AES

# pip install pycryptodome
from Crypto.Util.Padding import unpad
import ssl
from requests.adapters import HTTPAdapter

# SSL fix for KIS API (Windows OpenSSL 3.0+ 대응 및 인증서 우회)
class KISAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        context.set_ciphers('DEFAULT@SECLEVEL=1')
        context.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        kwargs['ssl_context'] = context
        return super().init_poolmanager(*args, **kwargs)

_session = requests.Session()
_session.mount('https://', KISAdapter())


def clearConsole():
    return os.system("cls" if os.name in ("nt", "dos") else "clear")

key_bytes = 32
config_root = os.path.join(os.path.expanduser("~"), "KIS", "config")
token_tmp = os.path.join(
    config_root, f"KIS{datetime.today().strftime('%Y%m%d')}"
)  # 토큰 로컬저장시 파일명 년월일

# 접근토큰 관리하는 파일 존재여부 체크, 없으면 생성
if not os.path.exists(config_root):
    os.makedirs(config_root, exist_ok=True)

if not os.path.exists(token_tmp):
    f = open(token_tmp, "w+")
    f.close() 

# 프로젝트 로컬 경로를 우선적으로 참조하도록 수정
config_root = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(config_root, "kis_devlp.yaml")

if not os.path.exists(config_path):
    config_path = os.path.join(config_root, "strategy_builder", "kis_devlp.yaml")

if os.path.exists(config_path):
    with open(config_path, encoding="UTF-8") as f:
        _cfg = yaml.load(f, Loader=yaml.FullLoader)
else:
    # 깃허브 액션 등 보안 환경을 위해 환경 변수에서 로드
    logging.info("config file not found. Loading from environment variables...")
    _cfg = {
        "my_app": os.environ.get("KIS_MY_APP", ""),
        "my_sec": os.environ.get("KIS_MY_SEC", ""),
        "paper_app": os.environ.get("KIS_PAPER_APP", ""),
        "paper_sec": os.environ.get("KIS_PAPER_SEC", ""),
        "my_htsid": os.environ.get("KIS_MY_HTSID", ""),
        "my_acct_stock": os.environ.get("KIS_MY_ACCT_STOCK", os.environ.get("KIS_ACCOUNT_NO", "")),
        "my_paper_stock": os.environ.get("KIS_MY_PAPER_STOCK", ""),
        "my_prod": os.environ.get("KIS_MY_PROD", "01"),
        "my_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "prod": "https://openapi.koreainvestment.com:9443",
        "vps": "https://openapivts.koreainvestment.com:29443",
        "ops": "ws://ops.koreainvestment.com:21000",
        "vops": "ws://ops.koreainvestment.com:31000"
    }

_TRENV = tuple()
_last_auth_time = datetime.now()
_autoReAuth = False
_DEBUG = False

def get_approval(key, secret):
    """
    Websocket 접속키 발급
    """
    url = _cfg["prod"] if not _isPaper else _cfg["vps"]
    url = f"{url}/oauth2/Approval"
    headers = {"Content-Type": "application/json; charset=UTF-8"}
    body = {"grant_type": "client_credentials", "appkey": key, "secretkey": secret}
    res = _session.post(url, headers=headers, data=json.dumps(body))
    try:
        return res.json()["approval_key"]
    except:
        return None
_isPaper = False
_smartSleep = 0.1

# Rate Limiter: 모든 REST API 호출을 직렬화하여 초당 제한 준수
import threading

_rate_lock = threading.Lock()
_last_api_call_time = 0.0

# 기본 헤더값 정의
_base_headers = {
    "Content-Type": "application/json",
    "Accept": "text/plain",
    "charset": "UTF-8",
    "User-Agent": _cfg["my_agent"],
}


# 토큰 발급 받아 저장 (토큰값, 토큰 유효시간,1일, 6시간 이내 발급신청시는 기존 토큰값과 동일, 발급시 알림톡 발송)
def save_token(my_token, my_expired):
    valid_date = datetime.strptime(my_expired, "%Y-%m-%d %H:%M:%S")
    with open(token_tmp, "w", encoding="utf-8") as f:
        f.write(f"token: {my_token}\n")
        f.write(f"valid-date: {valid_date}\n")


# 토큰 확인 (토큰값, 토큰 유효시간_1일, 6시간 이내 발급신청시는 기존 토큰값과 동일, 발급시 알림톡 발송)
def read_token():
    try:
        with open(token_tmp, encoding="UTF-8") as f:
            tkg_tmp = yaml.load(f, Loader=yaml.FullLoader)
        exp_dt = datetime.strftime(tkg_tmp["valid-date"], "%Y-%m-%d %H:%M:%S")
        now_dt = datetime.today().strftime("%Y-%m-%d %H:%M:%S")
        if exp_dt > now_dt:
            return tkg_tmp["token"]
        else:
            return None
    except Exception:
        return None


# 토큰 유효시간 체크해서 만료된 토큰이면 재발급처리
def _getBaseHeader():
    if _autoReAuth:
        reAuth()
    return copy.deepcopy(_base_headers)


# 가져오기 : 앱키, 앱시크리트, 종합계좌번호(계좌번호 중 숫자8자리), 계좌상품코드(계좌번호 중 숫자2자리), 토큰, 도메인
def _setTRENV(cfg):
    nt1 = namedtuple(
        "KISEnv",
        ["my_app", "my_sec", "my_acct", "my_prod", "my_htsid", "my_token", "my_url", "my_url_ws", "my_app_key"],
    )
    d = {
        "my_app": cfg["my_app"],
        "my_sec": cfg["my_sec"],
        "my_acct": cfg["my_acct"],
        "my_prod": cfg["my_prod"],
        "my_htsid": cfg["my_htsid"],
        "my_token": cfg["my_token"],
        "my_url": cfg["my_url"],
        "my_url_ws": cfg["my_url_ws"],
        "my_app_key": get_approval(cfg["my_app"], cfg["my_sec"])
    }
    global _TRENV
    _TRENV = nt1(**d)


def isPaperTrading():  # 모의투자 매매
    return _isPaper


# 실전투자면 'prod', 모의투자면 'vps'를 셋팅 하시기 바랍니다.
def changeTREnv(token_key, svr="prod", product=_cfg["my_prod"]):
    cfg = dict()
    global _isPaper
    if svr == "prod":  # 실전투자
        ak1 = "my_app"
        ak2 = "my_sec"
        _isPaper = False
        _smartSleep = 0.05
    elif svr == "vps":  # 모의투자
        ak1 = "paper_app"
        ak2 = "paper_sec"
        _isPaper = True
        _smartSleep = 0.5

    cfg["my_app"] = _cfg[ak1]
    cfg["my_sec"] = _cfg[ak2]

    if svr == "prod" and product == "01":
        cfg["my_acct"] = _cfg["my_acct_stock"]
    elif svr == "prod" and product == "03":
        cfg["my_acct"] = _cfg["my_acct_future"]
    elif svr == "vps" and product == "01":
        cfg["my_acct"] = _cfg["my_paper_stock"]
    elif svr == "vps" and product == "03":
        cfg["my_acct"] = _cfg["my_paper_future"]

    cfg["my_prod"] = product
    cfg["my_htsid"] = _cfg["my_htsid"]
    cfg["my_url"] = _cfg[svr]

    try:
        my_token = _TRENV.my_token
    except AttributeError:
        my_token = ""
    cfg["my_token"] = my_token if token_key else token_key
    cfg["my_url_ws"] = _cfg["ops" if svr == "prod" else "vops"]

    _setTRENV(cfg)


def _getResultObject(json_data):
    _tc_ = namedtuple("res", json_data.keys())
    return _tc_(**json_data)


# Token 발급
def auth(svr="prod", product=_cfg["my_prod"], url=None):
    p = {"grant_type": "client_credentials"}
    if svr == "prod":
        ak1 = "my_app"
        ak2 = "my_sec"
    elif svr == "vps":
        ak1 = "paper_app"
        ak2 = "paper_sec"

    p["appkey"] = _cfg[ak1]
    p["appsecret"] = _cfg[ak2]

    saved_token = read_token()
    if saved_token is None:
        url = f"{_cfg[svr]}/oauth2/tokenP"
        # _getBaseHeader() 대신 _base_headers를 직접 사용하여 재귀 방지
        res = _session.post(
            url, data=json.dumps(p), headers=_base_headers, verify=False, timeout=30
        )
        rescode = res.status_code
        if rescode == 200:
            my_token = _getResultObject(res.json()).access_token
            my_expired = _getResultObject(res.json()).access_token_token_expired
            save_token(my_token, my_expired)
        else:
            print(f"Get Authentification token fail! ({rescode})")
            return
    else:
        my_token = saved_token

    changeTREnv(my_token, svr, product)
    _base_headers["authorization"] = f"Bearer {my_token}"
    _base_headers["appkey"] = _TRENV.my_app
    _base_headers["appsecret"] = _TRENV.my_sec

    global _last_auth_time
    _last_auth_time = datetime.now()


def reAuth(svr="prod", product=_cfg["my_prod"]):
    n2 = datetime.now()
    if (n2 - _last_auth_time).seconds >= 86400:
        auth(svr, product)


def getEnv():
    return _cfg

def getTREnv():
    return _TRENV

def set_order_hash_key(h, p):
    url = f"{getTREnv().my_url}/uapi/hashkey"
    res = _session.post(url, data=json.dumps(p), headers=h, verify=False, timeout=30)
    if res.status_code == 200:
        h["hashkey"] = _getResultObject(res.json()).HASH

class APIResp:
    def __init__(self, resp):
        self._rescode = resp.status_code
        self._resp = resp
        self._header = self._setHeader()
        self._body = self._setBody()
        self._err_code = self._body.msg_cd if hasattr(self._body, 'msg_cd') else ""
        self._err_message = self._body.msg1 if hasattr(self._body, 'msg1') else ""

    def _setHeader(self):
        fld = {x: self._resp.headers.get(x) for x in self._resp.headers.keys() if x.islower()}
        return namedtuple("header", fld.keys())(**fld)

    def _setBody(self):
        return namedtuple("body", self._resp.json().keys())(**self._resp.json())

    def getHeader(self): return self._header
    def getBody(self): return self._body
    def isOK(self):
        try: return self.getBody().rt_cd == "0"
        except: return False
    def printError(self, url):
        print(f"Error {self._rescode} at {url}")
        print(f"Code: {self._err_code}, Message: {self._err_message}")

def _url_fetch(api_url, ptr_id, tr_cont, params, appendHeaders=None, postFlag=False, hashFlag=True):
    global _last_api_call_time
    with _rate_lock:
        now = time.monotonic()
        elapsed = now - _last_api_call_time
        if elapsed < _smartSleep: time.sleep(_smartSleep - elapsed)
        _last_api_call_time = time.monotonic()

    url = f"{getTREnv().my_url}{api_url}"
    headers = _getBaseHeader()
    tr_id = ptr_id
    if ptr_id[0] in ("T", "J", "C") and isPaperTrading():
        tr_id = "V" + ptr_id[1:]
    headers["tr_id"] = tr_id
    headers["custtype"] = "P"
    headers["tr_cont"] = tr_cont

    if appendHeaders: headers.update(appendHeaders)

    if postFlag:
        if hashFlag: set_order_hash_key(headers, params)
        res = _session.post(url, headers=headers, data=json.dumps(params), verify=False, timeout=30)
    else:
        res = _session.get(url, headers=headers, params=params, verify=False, timeout=30)

    return APIResp(res)
