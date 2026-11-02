from fastapi import APIRouter

from app.schemas.health import HealthResponse, ModelHealth
from app.services import help_prediction, prediction
from app.services.allocation_prediction import allocation_model_available
from app.services.object_detect import detection_runtime_ready

router = APIRouter(tags=["health"])


def _flood_model_available() -> bool:
    try:
        prediction.load_model()
    except prediction.ModelUnavailableError:
        return False
    return True


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="hydroflow-api",
        version="0.1.0",
        models=ModelHealth(
            flood=_flood_model_available(),
            help=help_prediction.help_model_available(),
            allocation=allocation_model_available(),
            object_detect=detection_runtime_ready(),
        ),
    )
