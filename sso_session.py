import functools
import html
import unittest

import requests, urllib, json, time, re
from urllib import parse

"""
Basic usage:
from sso_session import bmw_sso_session
my_session = bmw_sso_session(<bmw_app_url>,<q-number>,<password>)
my_session.get(<bmw_app_url_api_endpoint>, verify=False)  # You *should* setup the trusted CAs properly so verify=False is not required
"""


def _get_request_url(base_url, request_params=None):
    if isinstance(request_params, dict):
        request_params = urllib.parse.urlencode(request_params)
    return "{}?{}".format(base_url, request_params)


def _parse_get_parameters(url):
    url_parsed = urllib.parse.urlparse(url)
    get_params = urllib.parse.parse_qs(url_parsed.query)
    return {k: v[0] if isinstance(v, list) else v for k, v in get_params.items()}


def _sanitize_html(text):
    return html.unescape(text).replace('\n', '').replace('\r', '')


def _get_hidden_inputs(html_text):
    inputs_by_name_re = re.findall(r'input[^>]*hidden[^>]*name="([^"]+)"[^>]*value="([^"]+)"', html_text)
    named_inputs = {n: _sanitize_html(v) for n, v in inputs_by_name_re}
    inputs_by_id_re = re.findall(r'input[^>]*hidden[^>]*id="([^"]+)".*value="([^"]+)"', html_text)
    id_inputs = {n: _sanitize_html(v) for n, v in inputs_by_id_re}
    return id_inputs | named_inputs


def _process_auto_form(html_text, session):
    form_re = re.findall(r'<form method="(POST|GET|post|get)".*action="([^"]+)"', html_text)
    if not form_re:
        return
    method, url = form_re[0]
    url = _sanitize_html(url)
    form_dict = _get_hidden_inputs(html_text)
    if method.lower() == "get":
        return session.get(url, verify=False)
    elif method.lower() == "post":
        return session.post(url, data=form_dict, verify=False)


def _callback_iteration(session: requests.Session, auth_url, auth_bundle=None, responses=None):
    if responses is None:
        responses = {}
    if auth_bundle:
        for callback in auth_bundle["callbacks"]:
            if callback["type"] in responses:
                response = responses[callback["type"]]
                if callable(responses[callback["type"]]):
                    response = responses[callback["type"]]()
                if isinstance(responses[callback["type"]], dict):
                    response = responses[callback["type"]][callback['output'][0]['value']]
                if "input" in callback:
                    callback["input"][0]["value"] = response
    resp_cb = session.post(auth_url, verify=False, json=auth_bundle)
    return json.loads(resp_cb.content)


def bmw_sso_session(app_url: str, username: str, password: str, strong_auth=False,
                    strong_auth_type: str = "mobile", session: requests.Session = None) -> requests.Session:
    """
    Allows creating a session that is logged in via bmw sso and can access all the nice APIs you can!

    :param app_url: URL of the app you're trying to reach. Make sure that the URL forwards to the sso-page
    :param username: Your q-number
    :param password: Your tss-password or PIN (strong-auth)
    :param strong_auth: Whether to use strong_auth or not. Some pages may only work with or without it
    :param strong_auth_type: Can be 'mobile' or 'yubikey'; Only takes effect if strong_auth is set to True. Some pages may only work with one
    :param session: A requests.Session. If session is None a new session is created.
    :return: Returns the session in a (hopefully) logged in state
    """

    if session is None:
        session = requests.Session()

    """
    1. Open app and get redirected to login page
    """
    resp = session.get(app_url, allow_redirects=True, verify=False)
    redirected_app_url = resp.url  # we'll have to go back here at the end

    """
    2. Figure out parameters of bmwgroup sso auth page.
    These parameters will all be passed as get-params to https://auth.bmwgroup.net/auth/json/realms/root/realms/intranetb2x/authenticate
    """
    resp = _process_auto_form(resp.text, session)
    if resp:
        hidden_inputs = _get_hidden_inputs(resp.text)
    if resp and hidden_inputs and "loginUrl" in hidden_inputs:
        login_url = hidden_inputs["loginUrl"]
        get_params = _parse_get_parameters(login_url)
    else:
        get_params = {"goto": redirected_app_url}
    if strong_auth:
        get_params.update({"authIndexType": "service", "authIndexValue": "strongAuth4000Service"})
    if "realm" in get_params:
        del get_params["realm"]
    if not "AMAuthCookie" in get_params:  # Not required, but let's keep it in case
        get_params["AMAuthCookie"] = ""
    auth_url = _get_request_url("https://auth.bmwgroup.net/auth/json/realms/root/realms/intranetb2x/authenticate",
                                request_params=get_params)

    """
    3. Do callback iterations. These are the inputs in the familiar SSO-page, where you enter username/password,
    press the yubikey etc
    """
    responses = {"NameCallback": username, "PasswordCallback": str(password), "ChoiceCallback": 1,
                 "ConfirmationCallback": 100,
                 "PollingWaitCallback": functools.partial(time.sleep, 5)}
    auth_bundle = _callback_iteration(session, auth_url)
    if strong_auth_type == "yubikey":
        responses["ChoiceCallback"] = 0  # Probably choice callback should be selected based on the authbundle
        responses["PasswordCallback"] = {"AEP PIN": str(password), "HOTP (Yubikey)": input("Press Yubikey")}
    max_iterations = 8
    while auth_bundle and "callbacks" in auth_bundle:
        max_iterations -= 1
        if max_iterations < 0:
            assert False, "Could not go through bmw auth callbacks within 8 iterations"
        auth_bundle = _callback_iteration(session, auth_url, auth_bundle, responses)

    """
    4. Get token by executing the forms of the redirected page
    """
    redirect_url_parsed = urllib.parse.urlparse(redirected_app_url)
    redirect_get_params = urllib.parse.parse_qs(redirect_url_parsed.query)
    if "goto" in redirect_get_params:
        redirected_app_url = redirect_get_params["goto"][0]

    resp = session.get(redirected_app_url, verify=False)
    while resp:
        resp = _process_auto_form(resp.text, session)

    return session


class TestSSO(unittest.TestCase):

    @staticmethod
    def _verify_login(session: requests.Session, test_url: str, required_field: str):
        resp = session.get(test_url, verify=False)
        assert resp.status_code == 200, f"Did not get a status code 200: {resp.status_code}"
        try:
            data = json.loads(resp.text)
        except:
            assert False, f"Did not receive valid json: {resp.text}"
        assert required_field in data, f"{required_field} not found: {data}"

    def setUp(self):
        try:
            with open("login_info.txt", "r") as login_file:
                user_data = json.loads(login_file.read())
                self.username = user_data["username"]
                self.password = user_data["password"]
                self.pin = user_data["strong_pin"]
        except:
            assert False, "In order to run the tests you need to have a file login_info.txt with content `{'username':'<q-number>','password':'<tss-password>','pin':'<strong_auth_pin>'}`"

    def test_appcockpit(self):
        ac_session = bmw_sso_session("https://appcockpit.bmwgroup.net/auth/authenticate", self.username, self.password,
                                     strong_auth=False)
        self._verify_login(ac_session, "https://appcockpit.bmwgroup.net/api/oap/user-view/user-data", "profile")

    def test_octane(self):
        oc_session = bmw_sso_session("https://octane-prod.bmwgroup.net", self.username, self.password,
                                     strong_auth=False)
        self._verify_login(oc_session,
                           f"https://octane-prod.bmwgroup.net/api/shared_spaces/1002/workspaces/2001/workspace_users?fields=name%2Cid&query=%22%28name%3D%27{self.username}%27%29%22",
                           "total_count")

    def test_swhrl(self):
        swhrl_session = bmw_sso_session("https://swhrl.bmwgroup.net/webapi/hrlres/buildVersion", self.username,
                                        self.pin, strong_auth=True, strong_auth_type='mobile')
        self._verify_login(swhrl_session, "https://swhrl.bmwgroup.net/webapi/hrlres/buildVersion", "version")


def main():
    unittest.main()


if __name__ == "__main__":
    main()
