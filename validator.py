import re
import json
from collections import namedtuple

import pendulum


class ResponseValidator:
    SwaggerTypeToPythonType = {
        "integer": int,
        "string": str,
        "boolean": bool,
        "number": float,
    }

    def __init__(self, swagger):
        """
        :param swagger: inited swagger
        """
        self.swagger = swagger
        self.apispecs = None
        self.path_to_path_regex = {}
        self.parsed_url_to_path = {}

    def get_apispecs(self):
        if self.apispecs is None:
            self.apispecs = self.swagger.get_apispecs()
        return self.apispecs

    @classmethod
    def parse_url(cls, url):
        url = url.split("?")[0]
        if not url.startswith("/"):
            url = "/" + url

        return url

    def find_apispec(self, url):
        parsed_url = self.parse_url(url)

        if parsed_url in self.parsed_url_to_path:
            return self.get_apispecs()["paths"][self.parsed_url_to_path[parsed_url]]

        for path, apispec in self.get_apispecs()["paths"].items():
            if path in self.path_to_path_regex:
                path_regex = self.path_to_path_regex[path]
            else:
                path_regex = re.sub("{[^/]*}", "[^/]+?", path) + "$"
                self.path_to_path_regex[path] = path_regex

            if re.findall(path_regex, parsed_url):
                self.parsed_url_to_path[parsed_url] = path
                return apispec

    def validate_response(self, url, response, method="get", code=200):
        apispec = self.find_apispec(url)

        try:
            apispec_response = apispec[method]["responses"][str(code)]["schema"][
                "properties"
            ]
        except KeyError as err:
            if apispec[method]["responses"][str(code)] == {"description": "OK"}:
                apispec_response = {}
            else:
                raise err

        self._validate_object(apispec_response, response)

    def _fetch_ref(self, ref):
        ref_obj = self.get_apispecs()
        for ref_i in ref[2:].split("/"):
            ref_obj = ref_obj[ref_i]
        return ref_obj

    def _fetch_all_of(self, all_of: list):
        _obj = {}
        for i in all_of:
            if "$ref" in i:
                ref_obj = self.get_apispecs()
                for ref_i in i["$ref"][2:].split("/"):
                    ref_obj = ref_obj[ref_i]
                _obj.update(ref_obj["properties"])

            elif "properties" in i:
                _obj.update(i["properties"])

        return _obj

    def _validate_object(self, swagger_obj, res_obj):
        for k, v in swagger_obj.items():
            assert k in res_obj
            if "$ref" in v:
                v = self._fetch_ref(v["$ref"])
            if v["type"] == "array":
                assert type(res_obj[k]) == list
                if len(res_obj[k]) > 0:
                    if "properties" in v["items"]:
                        self._validate_object(v["items"]["properties"], res_obj[k][0])

                    elif "allOf" in v["items"]:
                        _obj = self._fetch_all_of(v["items"]["allOf"])
                        self._validate_object(_obj, res_obj[k][0])

            elif v["type"] == "object":
                if "properties" in v:
                    self._validate_object(v["properties"], res_obj[k])

                elif "allOf" in v:
                    _obj = self._fetch_all_of(v["allOf"])
                    self._validate_object(_obj, res_obj[k])
            else:
                expected_type = self.SwaggerTypeToPythonType.get(v["type"])
                if expected_type:
                    if v.get("nullable"):
                        assert res_obj[k] is None or type(res_obj[k]) == expected_type
                    else:
                        assert type(res_obj[k]) == expected_type