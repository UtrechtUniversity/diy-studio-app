# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

import asyncio
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.cloud_storage import CloudStorageManager


class UploadJob:
    def __init__(self, id, file_name):
        self.status = "queued"
        self.id = id
        self.file_name = file_name
        self.retry_attempts = 0
        
    def get_status(self) -> str:
        # self.status should be one of the following:
        # * str: "queued"
        # * str: "wait for drive space"
        # * str: percentage of completion
        # * str: "uploaded"
        return self.status
    
    def set_status(self, newstatus):
        self.status = newstatus


@dataclass
class CloudStorageItem:
    name: str
    id: str


@dataclass
class CloudStorageDirContent:
    dirs: list
    files: list


class CloudStorageProvider():
    def __init__(self, manager: "CloudStorageManager", config):
        self._upload_executor = ThreadPoolExecutor(max_workers=1)
        self._upload_lock = asyncio.Lock()
        self.LOGIN_TIMEOUT = config.login_timeout
        self.upload_queue = deque()
        self.authenticated = False
        self.credential = None
        self.download_id = 1
        self.downloaded_files = []
        self.manager = manager
        self.new_upload_job_id = 0
        self.upload_attempts = 0
        self.uploaded_files = []
        self.space_left = 0

    async def authenticate(self):
        raise NotImplementedError

    async def download_file(self, item: CloudStorageItem):
        raise NotImplementedError

    async def list_files(self, dir_id=None):
        raise NotImplementedError

    def logout(self):
        raise NotImplementedError

    def create_upload_job(self, file_name):
        raise NotImplementedError

    async def process_upload_queue(self):
        raise NotImplementedError

