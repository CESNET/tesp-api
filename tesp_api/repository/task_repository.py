from typing import Dict, Any

from pymonad.maybe import Maybe, Nothing
from pymongo import ReturnDocument
from pymonad.promise import Promise
from bson.objectid import ObjectId
from fastapi.encoders import jsonable_encoder
from motor.motor_asyncio import AsyncIOMotorClient

from tesp_api.repository.error import handle_data_layer_error
from tesp_api.utils.functional import maybe_of
from tesp_api.config.properties import properties
from tesp_api.repository.model.task import RegisteredTesTask, TesTaskState


async def get_mongo_client() -> AsyncIOMotorClient:
    mongo_client = AsyncIOMotorClient(properties.db.mongodb_uri)
    return mongo_client


class TaskRepository:

    def __init__(self):
        self._client = None
        self._tasks = None

    async def init(self):
        self._client = await get_mongo_client()
        self._tasks = self._client.tesp["tasks"]

    def create_task(self, task: RegisteredTesTask) -> Promise:
        task = jsonable_encoder(task, by_alias=True, exclude={"id"})
        return Promise(lambda resolve, reject: resolve(task)) \
            .then(self._tasks.insert_one) \
            .map(lambda created_task: created_task.inserted_id)\
            .catch(handle_data_layer_error)

    def update_task(self, search_query: Dict[str, Any],
                    update_query: Dict[str, Any]) -> Promise:
        return Promise(lambda resolve, reject: resolve((search_query, update_query)))\
            .then(lambda search_and_update_query: self._tasks.find_one_and_update(
                search_and_update_query[0],
                search_and_update_query[1],
                return_document=ReturnDocument.AFTER
            )).map(lambda task: maybe_of(task)
                   .map(lambda _task: RegisteredTesTask(**task)))\
            .catch(handle_data_layer_error)

    def update_task_state(
            self,
            task_id: ObjectId,
            old_state: TesTaskState,
            new_state: TesTaskState
        ) -> Promise:
        search_query = {'_id': task_id, "state": old_state}
        update_query = {'$set': {'state': new_state}}
        return self.update_task(search_query, update_query)

    def get_task(
            self,
            author: Maybe[str],
            search_query: Dict[str, Any]
            ) -> Promise:
        full_search_query = dict()
        full_search_query.update(author.maybe({}, lambda a: {'author': a}))
        full_search_query.update(search_query)

        return Promise(lambda resolve, reject: resolve(full_search_query)) \
            .then(self._tasks.find_one) \
            .map(lambda task: maybe_of(task)
                 .map(lambda _task: RegisteredTesTask(**_task)))\
            .catch(handle_data_layer_error)

    def get_tasks(
            self,
            author: Maybe[str],
            page_size: Maybe[int] = Nothing,
            page_token: Maybe[ObjectId] = Nothing,
            search_query: Maybe[Dict[str, Any]] = Nothing
            ) -> Promise:
        full_search_query = dict()
        full_search_query.update(author.maybe({}, lambda a: {'author': a}))
        full_search_query.update(page_token.maybe({}, lambda _page_token: {'_id': {'$gt': _page_token}}))
        full_search_query.update(search_query.maybe({}, lambda x: x))

        return Promise(lambda resolve, reject: resolve((page_size, full_search_query))) \
            .then(lambda size_and_query: size_and_query[0].maybe(
                    self._tasks.find(size_and_query[1]),
                    lambda x: self._tasks.find(size_and_query[1]).limit(x)
                 ).to_list(None)
            ).map(lambda found_tasks: list(map(lambda task: RegisteredTesTask(**task), found_tasks))) \
            .map(lambda found_tasks: (found_tasks, found_tasks[-1].id if found_tasks else None))\
            .catch(handle_data_layer_error)

    def cancel_task(
            self,
            p_author: Maybe[str],
            task_id: ObjectId
            ) -> Promise:
        full_search_query = dict()
        full_search_query.update({'_id': task_id})
        full_search_query.update(p_author.maybe({}, lambda a: {'author': a}))

        return Promise(lambda resolve, reject: resolve(full_search_query)) \
            .then(self._tasks.find_one) \
            .then(lambda _task: self.update_task(
                {'_id': task_id},
                {'$set': {'state': TesTaskState.CANCELED}}
            )).map(lambda updated_task: updated_task
                   .map(lambda _updated_task: _updated_task.id))\
            .catch(handle_data_layer_error)


task_repository = TaskRepository()
