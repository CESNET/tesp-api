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

    def get_task(
            self,
            p_author: Maybe[str],
            search_query: Dict[str, Any]
            ) -> Promise:
        author = p_author.maybe({}, lambda a: {'author': a})
        return Promise(lambda resolve, reject: resolve({**search_query, **author})) \
            .then(self._tasks.find_one) \
            .map(lambda task: maybe_of(task)
                 .map(lambda _task: RegisteredTesTask(**_task)))\
            .catch(handle_data_layer_error)

    def get_tasks(
            self,
            p_author: Maybe[str],
            p_size: Maybe[int] = Nothing,
            p_token: Maybe[ObjectId] = Nothing,
            search_query: Maybe[Dict[str, Any]] = Nothing
            ) -> Promise:
        def to_size_and_query():
            token_query = p_token.maybe({}, lambda _p_token: {'_id': {'$gt': _p_token}})
            _search_query = search_query.maybe({}, lambda x: x)
            author = p_author.maybe({}, lambda a: {'author': a})
            return p_size, {**token_query, **_search_query, **author}
        return Promise(lambda resolve, reject: resolve(to_size_and_query())) \
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
        _id = {'_id': task_id}
        author = p_author.maybe({}, lambda _a: {'author': _a})
        return Promise(lambda resolve, reject: resolve({
                **_id,
                **author
            })).then(self._tasks.find_one) \
            .then(lambda _task: self.update_task(
                {'_id': task_id},
                {'$set': {'state': TesTaskState.CANCELED}}
            )).map(lambda updated_task: updated_task
                   .map(lambda _updated_task: _updated_task.id))\
            .catch(handle_data_layer_error)


task_repository = TaskRepository()
