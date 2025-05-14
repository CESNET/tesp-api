import datetime

from pymonad.maybe import Just
from bson.objectid import ObjectId
from pymonad.promise import Promise
from fastapi.params import Depends
from fastapi import APIRouter, Body
# MODIFIED: Import JSONResponse
from fastapi.responses import Response, JSONResponse

from tesp_api.api.error import api_handle_error
from tesp_api.service.event_dispatcher import dispatch_event
from tesp_api.repository.task_repository import task_repository
from tesp_api.repository.model.task import TesTask, RegisteredTesTask, TesTaskState, TesTaskLog
from tesp_api.utils.functional import maybe_of, identity_with_side_effect
from tesp_api.api.model.task_service_info import TesServiceInfo, TesServiceType, TesServiceOrganization
from tesp_api.api.model.response_models import \
    TesGetAllTasksResponseModel,\
    TesCreateTaskResponseModel, \
    RegisteredTesTaskSchema,\
    TesGetAllTasksResponseSchema
from tesp_api.api.endpoints.endpoint_utils import \
    response_from_model, \
    descriptions, \
    view_query_params, \
    get_view, \
    list_query_params, resource_not_found_response, parse_verify_token

from tesp_api.utils.commons import Commons


router = APIRouter()


@router.post("/tasks",
             responses={200: {"description": "OK"}},
             response_model=TesCreateTaskResponseModel,
             description=descriptions["tasks-create"])
async def create_task(
        token_subject: str = Depends(parse_verify_token),
        tes_task: TesTask = Body(...)
        ) -> Response:
    task_to_create = RegisteredTesTask(
        **tes_task.dict(),
        state=TesTaskState.QUEUED,
        logs=[TesTaskLog(logs=[], outputs=[], system_logs=[])],
        creation_time=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        author=token_subject)
    return await task_repository.create_task(task_to_create)\
        .map(lambda task_id: identity_with_side_effect(
            task_id, lambda _task_id: dispatch_event(
                "queued_task",
                payload={
                    "task_id": _task_id,
                    "author": token_subject
                }
            )
        )).map(lambda task_id: response_from_model(TesCreateTaskResponseModel(id=str(task_id))))\
        .catch(api_handle_error)


@router.get("/tasks/{id}",
            responses={
                200: {"description": "Ok"},
                404: {"description": "Not found"}},
            response_model=RegisteredTesTaskSchema,
            description=descriptions["tasks-get"])
async def get_task(
        id: str,
        token_subject: str = Depends(parse_verify_token),
        query_params: dict = Depends(view_query_params)
        ) -> Response:
    return await Promise(lambda resolve, reject: resolve((
            maybe_of(token_subject),
            {'_id': ObjectId(id)}
        ))).then(lambda get_tasks_args: task_repository.get_task(*get_tasks_args))\
        .map(lambda found_task: found_task.maybe(
            resource_not_found_response(Just(f"Task[{id}] not found")),
            lambda _task: response_from_model(_task, get_view(query_params['view']))
        )).catch(api_handle_error)


@router.get("/tasks",
            responses={200: {"description": "Ok"}},
            response_model=TesGetAllTasksResponseSchema,
            description=descriptions["tasks-get-all"])
async def get_tasks(
        token_subject: str = Depends(parse_verify_token),
        query_params: dict = Depends(list_query_params)
        ) -> Response:
    return await Promise(lambda resolve, reject: resolve((
            maybe_of(token_subject),
            maybe_of(query_params['page_size']),
            maybe_of(query_params['page_token']).map(lambda _p_token: ObjectId(_p_token)),
            maybe_of(query_params['name_prefix']).map(lambda _name_prefix: {'name': {'$regex': f"^{_name_prefix}"}}))))\
        .then(lambda get_tasks_args: task_repository.get_tasks(*get_tasks_args))\
        .map(lambda tasks_and_token: response_from_model(
            TesGetAllTasksResponseModel(
                next_page_token=str(tasks_and_token[1]),
                tasks=list(map(lambda task: task.dict(**get_view(query_params['view'])), tasks_and_token[0])))
        )).catch(api_handle_error)


@router.post("/tasks/{id}:cancel",
             responses={200: {"description": "Ok"}}, # Consider adding a response_model if GA4GH TES spec defines one for cancel
             description=descriptions["tasks-delete"],)
async def cancel_task(
        id: str,
        token_subject: str = Depends(parse_verify_token),
        ) -> Response: # Return type is still Response, JSONResponse is a subclass
    return await Promise(lambda resolve, reject: resolve((
            maybe_of(token_subject),
            ObjectId(id)
    ))).then(lambda get_tasks_args: task_repository.cancel_task(*get_tasks_args))\
        .map(lambda task_id_maybe: 
             # MODIFIED: Use JSONResponse to ensure the body is "{}"
             # task_id_maybe here is likely a Maybe[ObjectId] or similar from cancel_task
             # We just need to return an empty JSON object on success.
             # If cancel_task itself can fail and we want to return a different status,
             # that logic would need to be built into how cancel_task's result is handled.
             # Assuming cancel_task raises an exception handled by .catch(api_handle_error) on failure.
             JSONResponse(content={}, status_code=200)
        )\
        .catch(api_handle_error)


@router.get("/service-info",
            responses={200: {"description": "Ok"}},
            description=descriptions["service-info"],
            response_model=TesServiceInfo)
async def get_service_info() -> TesServiceInfo: # FastAPI directly handles Pydantic model return
    return TesServiceInfo(
        id="fi.muni.cz.tesp",
        name="TESP",
        type=TesServiceType(
            group="org.ga4gh",
            artifact="tes",
            version="1.0.0"
        ),
        description="GA4GH TES Server implementation for Pulsar",
        organization=TesServiceOrganization(
            name="Faculty of Informatics, Masaryk University",
            url="https://www.fi.muni.cz/"
        ),
        contactUrl="https://www.fi.muni.cz/",
        documentationUrl="https://www.fi.muni.cz/",
        createdAt="2021-10-26T00:00:00Z",
        updatedAt="2021-10-26T00:00:00Z",
        environment="dev",
        version=Commons.get_service_version(),
        storage=["https://www.fi.muni.cz/"]
    )
