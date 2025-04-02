import time
from typing import Optional

from fastapi import status, HTTPException
from fastapi.responses import Response
from fastapi.security import OAuth2PasswordBearer, HTTPBasic, HTTPBasicCredentials
from pydantic.main import BaseModel
from pymonad.maybe import Nothing, Maybe
from fastapi.params import Query, Depends

from tesp_api.config.properties import properties
from tesp_api.repository.model.task import TesTaskView
from tesp_api.api.model.response_models import ErrorResponseModel
from tesp_api.service.error import OAuth2TokenError, BasicAuthError
from tesp_api.utils.token_validator import verify_token
from tesp_api.utils.basic_auth import verify_basic_auth

descriptions = {
    "tasks-create":  "Create a new task. The user provides a Task document, which the "
                     "server uses as a basis and adds additional fields.",
    "tasks-get":     "Get a single task, based on providing the exact task ID string.",
    "tasks-get-all": "List tasks tracked by the TES server. This includes queued, active"
                     " and completed tasks. How long completed tasks are stored by the"
                     " system may be dependent on the underlying implementation.",
    "tasks-delete":  "Cancel a task based on providing an exact task ID.",
    "service-info":  "Provides information about the service"
                     ", this structure is based on the standardized GA4GH"
                     " service info structure. In addition, this endpoint"
                     " will also provide information about customized storage"
                     " endpoints offered by the TES server."
}

query_descriptions = {
    "name_prefix": "OPTIONAL. Filter the list to include tasks where the name matches"
                   " this prefix. If unspecified, no task name filtering is done.",
    "page_size":   "OPTIONAL. Number of tasks to return in one page. Must be less than"
                   " 2048. Defaults to 256.",
    "page_token":  "OPTIONAL. Page token is used to retrieve the next page of results."
                   " If unspecified, returns the first page of results. See ListTasksResponse.next_page_token",
    "view":        "OPTIONAL. Affects the fields included in the returned Task messages. See TaskView below."
                   " - MINIMAL: Task message will include ONLY the fields: Task.Id Task.State"
                   " - BASIC: Task message will include all fields EXCEPT: Task.ExecutorLog.stdout"
                   " Task.ExecutorLog.stderr Input.content TaskLog.system_logs"
                   " - FULL: Task message includes all fields."
}

qry_var_name_prefix = Query(None, description=query_descriptions['name_prefix'])
qry_var_page_size = Query(256, description=query_descriptions['page_size'])
qry_var_page_token = Query(None, description=query_descriptions['page_token'])
qry_var_view = Query(TesTaskView.MINIMAL, description=query_descriptions['view'])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
basic_auth_scheme = HTTPBasic(auto_error=False)  # Basic Auth support


async def view_query_params(view: Optional[TesTaskView] = qry_var_view):
    return {"view": view}


async def list_query_params(name_prefix: Optional[str] = qry_var_name_prefix,
                            page_size: int = qry_var_page_size,
                            page_token: Optional[str] = qry_var_page_token,
                            view: dict = Depends(view_query_params)):
    return {
        "name_prefix": name_prefix,
        "page_size": page_size,
        "page_token": page_token,
        **view
    }


def parse_verify_token(
    token: str = Depends(oauth2_scheme),
    basic_credentials: HTTPBasicCredentials = Depends(basic_auth_scheme)
):
    if properties.basic_auth.enable:
        try:
            return verify_basic_auth(basic_credentials.username, basic_credentials.password)
        except BasicAuthError as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    if not properties.oauth.enable:
        return None

    try:
        return verify_token(token)
    except OAuth2TokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


def get_view(view: Optional[TesTaskView]) -> dict:
    return {
        TesTaskView.BASIC: {'exclude':
                            {'logs': {'__all__': {'system_logs': True, 'logs': {'__all__': {'stdout', 'stderr'}}}},
                             'inputs': {'__all__': {'content'}}}},
        TesTaskView.MINIMAL: {'include': {'id', 'state'}}
    }.get(view, {'exclude': {}})


def resource_not_found_response(message: Maybe[str] = Nothing):
    error = ErrorResponseModel(
        timestamp=int(time.time()),
        error="Not Found",
        status=status.HTTP_404_NOT_FOUND,
        message=message.maybe("", lambda x: x))
    return Response(error.json(), status_code=status.HTTP_404_NOT_FOUND, media_type='application/json')


def response_from_model(model: BaseModel, model_rules: dict = None) -> Response:
    return Response(model.json(**(model_rules if model_rules else {}), by_alias=False),
                    status_code=200, media_type='application/json')
