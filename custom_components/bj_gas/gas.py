import logging
import datetime
import json
import asyncio

_LOGGER = logging.getLogger(__name__)

DOMAIN = "https://zt.bjgas.com"

R_API_PATH = "/bjgas-server/r/api"
I_API_PATH = "/bjgas-server/i/api"

# 登录
OAUTH_URL = f"{DOMAIN}/bjgas-server/oauth/token?"
# 获取用户ID
USER_ID_URL = f"{DOMAIN}{I_API_PATH}/getUserId/"
# 获取用户燃气信息列表
USER_GAS_LIST_URL = f"{DOMAIN}{I_API_PATH}/nsgetUserGasListEncrypt/"
WEEK_QRY_URL = f"{DOMAIN}{I_API_PATH}/intelligent/getWeekQry?userCode="
STEP_QRY_URL = f"{DOMAIN}{R_API_PATH}?sysName=CCB&apiName=CM-MOB-IF07"
YEAR_QRY_URL = f"{DOMAIN}{I_API_PATH}/intelligent/getYearQry?userCode="
USER_INFO_URL = f"{DOMAIN}{I_API_PATH}/intelligent/queryUserInfo?userCode="

class AuthFailed(Exception):
    pass


class InvalidData(Exception):
    pass


class GASData:
    def __init__(self, session, config, store):
        self._session = session
        self._token = ""
        self._config = config
        self._store = store
        self._user_id = ""
        self.mobile = ""
        self._oauth_count = 0
        self._user_code_list = []
        self._info = {}

    def common_headers(self, authorization: bool=True):
        headers = {
            "Host": "zt.bjgas.com",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Accept-Language": "zh-cn, zh-Hans; q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 "
                          "(KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.7(0x1800072c) "
                          "NetType/WIFI Language/zh_CN",
            "Connection": "keep-alive"
        }
        if authorization:
            if self._token == "":
                raise AuthFailed("No token, please check your configuration and restart Home Assistant")
            headers["Authorization"] = f"Bearer {self._token}"
        return headers
    
    async def async_load_token(self):
        data = await self._store.async_load()
        if data and "access_token" in data:
            self._token = data["access_token"]
            return True
        else:
            return False
        
    async def async_save_token(self):
        data = await self._store.async_load()
        if data is None:
            data = {}
        data["access_token"] = self._token
        data["saved_at"] = datetime.datetime.now().isoformat()
        await self._store.async_save(data)

    async def async_oauth_token(self):
        headers = self.common_headers(authorization=False)
        oauth_params = self._config.get("oauth_params")
        r = await self._session.post(OAUTH_URL + oauth_params, headers=headers, timeout=10)
        if r.status == 200:
            result = json.loads(await r.read())
            if "access_token" in result:
                self._token = result["access_token"]
                await self.async_save_token()
            else:
                raise AuthFailed(f"oauth error: {result}")
        else:
            data = await r.read()
            raise AuthFailed(f"oauth response status_code = {r.status}, params = {oauth_params}, response = {data}")
        
    async def async_init_token(self):
        if self._token == "":
            load = await self.async_load_token()
            if not load:
                await self.async_oauth_token()
        
    async def is_invalid_token(self, res):
        if res.status == 401:
            result = json.loads(await res.read())
            if "error" in result and result["error"] == "invalid_token":
                _LOGGER.warning(f"Token is invalid, need to refresh token: {result['error_description']}")
                return True
        return False
    
    async def async_load_user_id(self):
        data = await self._store.async_load()
        if data and "user_id" in data:
            self._user_id = data["user_id"]
            return True
        else:
            return False

    async def async_save_user_id(self):
        data = await self._store.async_load()
        if data is None:
            data = {}
        data["user_id"] = self._user_id
        data["mobile"] = self.mobile
        await self._store.async_save(data)
    
    async def async_get_user_id(self):
        headers = self.common_headers()
        r = await self._session.get(USER_ID_URL + self._token, headers=headers, timeout=10)
        if r.status == 200:
            result = json.loads(await r.read())
            if result["success"]:
                data = result["rows"][0]
                self._user_id = data["userId"]
                self.mobile = data["mobile"]
                await self.async_save_user_id()
            else:
                raise InvalidData(f"async_get_user_id error: {result}")
        else:
            raise InvalidData(f"async_get_user_id response status_code = {r.status}")

    async def async_init_user_id(self):
        if self._user_id == "":
            load = await self.async_load_user_id()
            if not load:
                await self.async_get_user_id()

    async def async_get_gas_List(self):
        headers = self.common_headers()
        r = await self._session.get(USER_GAS_LIST_URL + self._user_id, headers=headers, timeout=10)
        if r.status == 200:
            result = json.loads(await r.read())
            if result["success"]:
                self._user_code_list = []
                for user_gas in result["rows"]:
                    user_code = user_gas["userCode"]
                    self._user_code_list.append(user_code)
                return result["rows"]
            else:
                raise InvalidData(f"async_get_gas_List error: {result}")
        else:
            # 刷新token 未知情况失败超过3次，抛出异常
            if self._oauth_count < 3 and await self.is_invalid_token(r):
                self._oauth_count += 1
                await self.async_oauth_token()
                await self.async_get_gas_List()
                # 获取成功重置计数器
                self._oauth_count = 0
                return
            raise InvalidData(f"async_get_gas_List response status_code = {r.status}")
            

    async def async_get_week(self, user_code):
        headers = self.common_headers()
        r = await self._session.get(WEEK_QRY_URL + user_code, headers=headers, timeout=10)
        if r.status == 200:
            result = json.loads(await r.read())
            if result["success"]:
                data = result["rows"][0]["infoList"]
                self._info[user_code]["daily_bills"] = data
            else:
                raise InvalidData(f"async_get_week error: {result}")
        else:
            raise InvalidData(f"async_get_week response status_code = {r.status}")

    async def async_get_year(self, user_code):
        headers = self.common_headers()
        r = await self._session.get(YEAR_QRY_URL + user_code, headers=headers, timeout=10)
        if r.status == 200:
            result = json.loads(await r.read())
            if result["success"]:
                data = result["rows"][0]["infoList"]
                self._info[user_code]["monthly_bills"] = data
            else:
                raise InvalidData(f"async_get_year error: {result}")
        else:
            raise InvalidData(f"async_get_year response status_code = {r.status}")

    async def async_get_userinfo(self, user_code):
        headers = self.common_headers()
        r = await self._session.get(USER_INFO_URL + user_code, headers=headers, timeout=10)
        if r.status == 200:
            result = json.loads(await r.read())
            if result["success"]:
                data = result["rows"][0]
                self._info[user_code]["last_update"] = data["fiscalDate"]
                self._info[user_code]["balance"] = float(data["remainAmt"])
                self._info[user_code]["battery_voltage"] = float(data["batteryVoltage"])
                self._info[user_code]["current_price"] = float(data["gasPrice"])
                self._info[user_code]["month_reg_qty"] = float(data["regQty"])
                self._info[user_code]["mtr_status"] = data["mtrStatus"]
            else:
                raise InvalidData(f"async_get_userinfo error: {result}")
        else:
            raise InvalidData(f"async_get_userinfo response status_code = {r.status}")

    async def async_get_step(self, user_code):
        headers = self.common_headers()
        headers["Content-Type"] = "application/json;charset=UTF-8"
        headers["Origin"] = "file://"
        json_date = {"CM-MOB-IF07": {"input": {"UniUserCode": f"{user_code}"}}}
        r = await self._session.post(STEP_QRY_URL, headers=headers, json=json_date, timeout=10)
        if r.status == 200:
            result = json.loads(await r.read())
            data = result["soapenv:Envelope"]["soapenv:Body"]["CM-MOB-IF07"]["output"]
            if float(data["Step1LeftoverQty"]) > 0:
                self._info[user_code]["current_level"] = 1
                self._info[user_code]["current_level_remain"] = float(data["Step1LeftoverQty"])
            else:
                self._info[user_code]["current_level"] = 2
                self._info[user_code]["current_level_remain"] = float(data["Step2LeftoverQty"])
            self._info[user_code]["year_consume"] = float(data["TotalSq"])
        else:
            raise InvalidData(f"async_get_step response status_code = {r.status}")

    async def async_get_data(self):
        self._info = {}
        await self.async_init_token()
        await self.async_init_user_id()
        await self.async_get_gas_List()
        for user_code in self._user_code_list:
            self._info[user_code] = {}
            await asyncio.gather(
                self.async_get_userinfo(user_code),
                self.async_get_week(user_code),
                self.async_get_year(user_code),
                self.async_get_step(user_code),
                return_exceptions=True
            )
            
        _LOGGER.debug(f"Data {self._info}")
        return self._info
