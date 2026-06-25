# Copyright © 2026 Utrecht University
# Licensed under the EUPL v1.2

"""
Module for interacting with Microsoft OneDrive.

We're using the official MS Graph SDK for Python to interact
with the Microsoft Graph REST API:
https://www.github.com/microsoftgraph-msgraph-sdk-python

Reference manual:
https://learn.microsoft.com/en-us/graph/api/overview?view=graph-rest-1.0

Installation:
python3 -m pip install azure-identity
python3 -m pip install msgraph-sdk

Microsoft has several ways to authenticate via the Graph
REST API. We are using the Interactive Provider, which means a
browser window will open in which each user can authenticate.
This is the safest option because we won't have to handle any
usernames, passwords and 2FA in this application.

The Graph SDK for Python uses Coroutines with asyncio. We run an
asyncio event loop in a separate thread:
* run_async_loop

The process for uploading files looks as follows:
CloudStorageManager.start_upload() will be called by RecorderManager
  > CloudStorageManager.add_to_uploads - adds the file to self.uploads
  > onedrive.create_upload_job - adds a new UploadJob to 
    onedrive.upload_queue
  > onedrive.process_upload_queue is called when no upload is currently
    running - we need a session per file
    > onedrive._upload_to_session adds the file to the upload session
        > when done uploading: UploadJob is removed from 
          onedrive.upload_queue and added to onedrive.uploaded_files
        > in case of an error: show error message and return
        > OnedriveManager.restart_upload_queue() can restart the queue
"""

import asyncio
import logging
import os
import requests
from . import Action
from azure.identity import InteractiveBrowserCredential
from modules.backends.cloud_storage.storage_base  import UploadJob, CloudStorageItem, CloudStorageDirContent, CloudStorageProvider
from msgraph import GraphServiceClient
from msgraph.generated.models.o_data_errors.o_data_error import ODataError
from msgraph.generated.drives.item.items.item.create_upload_session.create_upload_session_post_request_body import CreateUploadSessionPostRequestBody
from msgraph.generated.models.drive_item_uploadable_properties import DriveItemUploadableProperties
from os.path import exists, getsize
from time import sleep
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.cloud_storage import CloudStorageManager

logger = logging.getLogger(__name__)


class OneDriveStorage(CloudStorageProvider):
    def __init__(self, manager: "CloudStorageManager", config):
        super().__init__(manager, config)
        self.CLIENT_ID = config.client_id
        self.TENANT_ID = config.tenant_id
        self.SCOPES = ["Files.ReadWrite", "User.Read"]
        self.REDIRECT_URI = "http://localhost:8000"
        self.drive_id = None
        self.graph_client = None
        self.manager = manager
        self.root_item_id = ""

    async def _get_drive_info(self):
        """Retrieve OneDrive id and space_remaining"""
        try:
            drive = await self.graph_client.me.drive.get()
        except ODataError as e:
                logger.info(f"Error while fetching drive ID: {e}")
                self._handle_odataerror(e)
                return False
        else:
            if drive.id:
                self.drive_id = drive.id
            else:
                # No Drive ID?
                return False

            if drive.quota.remaining:
                self.space_left = drive.quota.remaining
                return True
            else:
                # Unable to retrieve drive quota
                return False
        
    async def _get_space_left(self):
        await self._get_drive_info()
        return self.space_left

    def _handle_odataerror(self, e):
        """Central handling of ODataErrors"""
        status = getattr(e, "response_status_code", None)
        code = getattr(getattr(e, "error", None), "code", None)

        if status == 401 or code in [
            "InvalidAuthenticationToken", "AuthenticationFailed"
        ]:
            # Token invalid
            logger.error("OneDrive : lost authentication")
            self.manager.route_call("gui_manager", "show_error", 407)
            
            # Reset login
            self.manager.route_call("gui_manager", "on_auth_lost")

        elif status == 403:
            logger.error("OneDrive : failed to obtain permissions")
            self.manager.route_call("gui_manager", "show_error", 407)

        else:
            logger.error(f"OneDrive : Graph error : {e}")

    async def _on_upload_finished(self, job):
        self.uploaded_files.append(job)

        # Remove from queue
        if self.upload_queue and self.upload_queue[0] is job:
            self.upload_queue.popleft()

        # Update info on shutdown screen
        self.manager.route_call(
            "gui_manager",
            "update_shutdown_info",
            len(self.upload_queue)
            )
        
        # If there's another job in the queue, start it
        if len(self.upload_queue) > 0:
            await self.process_upload_queue()

    async def _on_upload_failed(self, job):
        job.set_status("queued")
        logger.critical("CloudStorageManager : file upload failed ")
        self.manager.route_call("gui_manager", "show_error", 406)
        self.manager.schedule_queue_restart()

    def _upload_to_session(
            self, job, upload_url: str, file_path: str, start: int = 0
        ) -> bool:
        """Upload a file to a session that was created with process_upload_queue()"""
        # We must send a PUT request to the upload_session through
        # the upload url
        MAX_RETRIES = 5

        result = ""

        file_size = getsize(file_path)

        # Max chunk size must be a multiple of 320 KiB!
        # Adviced is a size between 5-10 MiB
        chunk_size = 320 * 1024 * 20
        
        with requests.Session() as s, open(file_path, "rb") as file:
            file.seek(start)

            while start < file_size:
                this_chunk_size = min(chunk_size, (file_size - start))
                end = start + this_chunk_size
                chunk = file.read(this_chunk_size)

                # end must indicate the position of the last byte
                # hence the -1
                header = {
                    "Content-Length": str(this_chunk_size),
                    "Content-Range": f"bytes {start}-{end - 1}/{file_size}"
                }

                try:
                    # This might wait forever if we don't specify a timeout
                    response = s.put(upload_url, headers=header, data=chunk,
                                            timeout=10)
                except (
                    requests.Timeout,
                    requests.ConnectionError,
                    requests.RequestException
                ) as e:
                    logger.error(f"OneDrive : upload to session failed : {e}")
                    job.retry_attempts += 1
                    if job.retry_attempts > MAX_RETRIES:
                        return False
                    sleep(5 * job.retry_attempts)
                    continue

                match response.status_code:
                    case 200 | 201:
                        # 200/201 = upload done
                        logger.info("OneDrive : upload successful")
                        # Reset retry_attempts
                        job.retry_attempts = 0
                        # Add to uploaded_files
                        job.set_status("uploaded")
                        return True
                    
                    case 202:
                        # 202 = busy uploading
                        completed = ((start + this_chunk_size)
                                        / file_size * 100)
                        completed_str = str(round(completed)) + "%"
                        logger.info(
                            f"OneDrive : uploading : {completed_str} "
                        )
                        job.set_status(completed_str)
                        
                        # Advance to next chunk
                        start += this_chunk_size
                        continue
                        
                    case 404:
                        # Somehow the upload session disappeared.
                        # We need to restart the entire session.
                        return False
                        
                    case _ if (response.status_code >= 500
                                and response.status_code < 600):
                        # Resume or retry uploads that fail due to
                        # connection interruptions or any 5xx errors
                        # including:
                        #    500 Internal Server Error
                        #    502 Bad Gateway
                        #    503 Service Unavailable
                        #    504 Gateway Timeout
                        job.retry_attempts += 1
                        if job.retry_attempts > MAX_RETRIES:
                            return False
                        sleep(5 * job.retry_attempts)
                        continue
                        
                # Other cases:
                return False
        return False
    
    async def authenticate(self):
        logger.info("OneDrive : starting auth process")
        
        if not self.manager.is_internet_available():
            self.manager.set_action(Action.IDLE)
            return

        if not self.authenticated:
            self.credential = InteractiveBrowserCredential(
                tenant_id=self.TENANT_ID,
                client_id=self.CLIENT_ID,
                redirect_uri=self.REDIRECT_URI,
                timeout=self.LOGIN_TIMEOUT
            )
            
            # GraphServiceClient is our object through which
            # we can access all things related to the authenticated
            # user's Microsoft account - in this case: OneDrive.
            self.graph_client = GraphServiceClient(self.credential, self.SCOPES)

            # This will trigger the actual browser login
            result = await self._get_drive_info()
            
            if not result:
                # Couldn't retrieve drive info
                logger.error("OneDrive : could not retrieve drive info")
                return False
            else:
                root_item = await self.graph_client.drives.by_drive_id(
                    self.drive_id
                ).root.get()
                
                self.root_item_id = root_item.id
                
                # Authentication must have been successful
                logger.info("OneDrive : authentication successful")
                self.authenticated = True
                return True
        else:
            # Already authenticated, no need to do anything
            logger.info("OneDrive : already authenticated")
            return True
    
    async def download_file(self, item: CloudStorageItem):

        file_path = ""

        if not self.authenticated:
            logger.error("OneDrive : user not authenticated")
            self.manager.route_call("gui_manager", "show_error", 404)
            return "error: user not authenticated"

        new_file = False

        while not new_file:
            file_path = os.path.join(
                self.manager.download_dir,
                "presentation_" + str(self.download_id)
            )

            if exists(file_path):
                # File exists. Increase ID and try again.
                # This should not happen as every download
                # gets a unique filename - but a restart of the app
                # might have been unable to remove older files
                logger.info(f"OneDrive : file already exists. "
                                "Trying another filename.")
                
                self.download_id += 1
            else:
                new_file = True
    
        try:
            file_content = await self.graph_client.drives.by_drive_id(
                self.drive_id
            ).items.by_drive_item_id(
                item.id
            ).content.get()

            # Save file contents. "wb" = write binary
            with open(file_path, "wb") as file:
                self.download_id += 1
                file.write(file_content)
                logger.info(f"OneDrive : file "
                                "has been downloaded")
                self.downloaded_files.append(item)
                return file_path

        except ODataError as e:
            logger.error(f"OneDrive : error while downloading file: "
                            f"{e}")
            self._handle_odataerror(e)
            return "error: download failed"

    async def list_files(self, dir_id=None):
        """Get directory contents and return these as CloudStorageDirContent object"""
        logger.info("OneDrive : attempting to list files")
        dirs = []
        files = []

        def append_items(items):
            for item in items:
                if item.folder:
                    # Item is a folder
                    if not item.name.endswith("@ Universiteit Utrecht"):
                        new_item = CloudStorageItem(item.name, item.id)
                        dirs.append(new_item)
                        # logger.info(f"Folder with id: {item.id}")
                elif item.file and (
                    item.name.endswith(".pptx") 
                    or item.name.endswith(".ppt")
                    or item.name.endswith(".odp")
                    ):
                    new_item = CloudStorageItem(item.name, item.id)
                    files.append(new_item)
                    # logger.info(f"Presentation with id: "
                    #             "{item.id}")

        if not self.authenticated:
            self.manager.route_call("gui_manager", "show_error", 404)
            return CloudStorageDirContent([], [])

        if dir_id == None:
            item_id = self.root_item_id
        else:
            item_id = dir_id
            logger.info("OneDrive : retrieving items in directory")

        # Upon success we"ll receive an object with
        # the first 200 items as driveItem objects:
        # result.value
        #   result.value.name
        #   result.value.id
        #   result.value.folder.childCount (if it"s a folder)
        #   result.value.size
        #   result.value.file
        # result.odata_next_link
        #
        # This last one will indicate that there are more results available
        # beyond the 200 that were returned.

        try:
            result = await self.graph_client.drives.by_drive_id(
                self.drive_id
            ).items.by_drive_item_id(
                item_id
            ).children.get()
            
            if result:
                append_items(result.value)

                while (result is not None
                        and result.odata_next_link is not None):
                    # More items available, let"s fetch those as well
                    result = await self.graph_client.drives.by_drive_id(
                        self.drive_id
                    ).items.by_drive_item_id(
                        item_id
                    ).children.with_url(
                        result.odata_next_link
                    ).get()
                    
                    if result:
                        append_items(result.value)

        except ODataError as e:
            logger.info("OneDrive : error while fetching drive items: "
                            f"{e}")
            self._handle_odataerror(e)

        return CloudStorageDirContent(dirs, files)

    def logout(self):
        logger.info("OneDrive : logged user out")
        self.authenticated = False
        self.drive_id = None
        self.credential = None
        self.graph_client = None
        self.root_item_id = ""
        self.upload_attempts = 0
        
    def create_upload_job(self, file_name):
        """Create an UploadJob object and add it to upload_queue"""
        job: UploadJob
        file_dir = self.manager.rec_dir_good
        file_path = os.path.join(file_dir, file_name)
            
        # Check if file exists
        if not exists(file_path):
            logger.critical("OneDrive : can't create upload job: "
                             + "file does not exist")
            logger.critical(file_path)
            return False
        
        else:         
            # Check if there's a job already with the same
            # file_dir and file_name
            for existing_job in self.upload_queue:
                if existing_job.file_name == file_name:
                    # Job exists in queue
                    job = existing_job
                    return job
                    
            for existing_job in self.uploaded_files:
                if existing_job.file_name == file_name:
                    # Job exists in queue
                    job = existing_job
                    return job
            
            # Create job
            upload_id = self.new_upload_job_id
            self.new_upload_job_id += 1
            job = UploadJob(upload_id, file_name)
            self.upload_queue.append(job)
            
            # Update text on shutdown screen
            self.manager.route_call(
                "gui_manager",
                "update_shutdown_info",
                len(self.upload_queue)
                )
                
            return job
         
    async def process_upload_queue(self):
        """Create a new remote session for the upload"""
        logger.info("OneDrive : starting upload session")
        async with self._upload_lock:
            loop = asyncio.get_running_loop()

            if not self.upload_queue or len(self.upload_queue) == 0:
                logger.warning(
                    "OneDrive : can't create upload session : "
                    "no items in self.upload_queue"
                )
                return
            
            if not self.manager.is_internet_available():
                return

            if not self.authenticated:
                logger.error(
                    "OneDrive: process_upload_queue : user not authenticated"
                )
                self.manager.route_call("gui_manager", "show_error", 404)
                return

            job = self.upload_queue[0]
            file_path = os.path.join(
                self.manager.rec_dir_good, job.file_name
            )

            # Check if there's enough space left in OneDrive
            # to upload this job
            space_left = await self._get_space_left()
            if space_left < os.path.getsize(file_path):
                logger.error("OneDrive : not enough space for upload job")
                job.set_status("waiting for drive space")
                self.manager.route_call("gui_manager", "show_error", 403)
                self.manager.schedule_queue_restart()
                return

            try:
                # Graph: create an upload session (necessary for large files)
                # conflictBehavior: "rename" adds a number after the filename
                # if a file with this name already exists
                uploadable_properties = DriveItemUploadableProperties(
                    additional_data = {
                        "@microsoft.graph.conflictBehavior": "rename"
                    }
                )

                upload_session_request_body = CreateUploadSessionPostRequestBody(
                    item = uploadable_properties
                )

                upload_session = await self.graph_client.drives.by_drive_id(
                    self.drive_id
                    ).items.by_drive_item_id(
                        "root:/" + job.file_name + ":"
                        ).create_upload_session.post(
                            upload_session_request_body
                        )
                
                logger.info(
                    "OneDrive : upload session started. Session will expire "
                    f"{upload_session.expiration_date_time}"
                )
                
                upload_url = upload_session.upload_url

            except ODataError as e:
                logger.error(f"OneDrive : upload error: {e}")
                self.manager.route_call("gui_manager", "show_error", 402)
                self._handle_odataerror(e)
                return
                
            except Exception:
                logger.exception(
                    "OneDrive : can't create upload session."
                )
                self.manager.route_call("gui_manager", "show_error", 402)
                return

            # Start blocking upload in worker thread
            success = await loop.run_in_executor(
                self._upload_executor,
                self._upload_to_session,
                job, upload_url, file_path, 0
            )

        if success:
            await self._on_upload_finished(job)
        else:
            await self._on_upload_failed(job)
