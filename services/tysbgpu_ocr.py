# -*- coding: utf-8 -*-

import base64
import json
import os
import ssl
from typing import List

try:
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
except ImportError:
    from urllib2 import Request, urlopen, HTTPError

from config.settings import get_settings

LOW_CONFIDENCE_THRESHOLD = 0.85


class OCRService:
    context = ssl._create_unverified_context()

    def __init__(self):
        settings = get_settings()
        self.api_url = settings.ocr_api_url
        self.params = {
            "configure": {
                "min_size": 16,
                "output_prob": True,
                "output_keypoints": False,
                "skip_detection": False,
                "without_predicting_direction": False,
            }
        }

    def get_img(self, img_file):
        if img_file.startswith("http"):
            return img_file
        with open(os.path.expanduser(img_file), "rb") as f:
            data = f.read()
        try:
            return str(base64.b64encode(data), "utf-8")
        except TypeError:
            return base64.b64encode(data)

    def posturl(self, headers, body):
        try:
            params = json.dumps(body).encode(encoding="UTF8")
            req = Request(self.api_url, params, headers)
            r = urlopen(req, context=self.context)
            return r.read().decode("utf8")
        except HTTPError as e:
            detail = e.read().decode("utf8")
            raise RuntimeError(f"OCR 接口错误 {e.code}: {detail}") from e

    def request_payload(self, img_file, params):
        appcode = get_settings().require_ocr_appcode()
        if params is None:
            params = {}
        img = self.get_img(img_file)
        body = dict(params)
        body["image"] = img

        headers = {
            "Authorization": f"APPCODE {appcode}",
            "Content-Type": "application/json; charset=UTF-8",
        }

        response = self.posturl(headers, body)
        json_response = json.loads(response)
        if not json_response.get("success", True) and "ret" not in json_response:
            raise RuntimeError(f"OCR 识别失败: {json_response}")

        text = ""
        probs: List[float] = []
        low_confidence_words: List[str] = []

        for item in json_response.get("ret", []):
            word = item.get("word", "")
            text += word
            prob = item.get("prob")
            if prob is not None:
                probs.append(float(prob))
                if float(prob) < LOW_CONFIDENCE_THRESHOLD and word.strip():
                    low_confidence_words.append(word)

        avg_confidence = sum(probs) / len(probs) if probs else 1.0
        return {
            "text": text,
            "low_confidence_words": low_confidence_words,
            "avg_confidence": round(avg_confidence, 3),
        }

    def request_with_meta(self, img_file, params):
        return self.request_payload(img_file, params)

    def request(self, img_file, params):
        return self.request_payload(img_file, params)["text"]
