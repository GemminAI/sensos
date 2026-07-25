from uuid import UUID

from sqlalchemy.orm import Session

from runtime.core.exceptions import NotFoundError
from runtime.db.tables import Experiment, Session as SessionModel
from runtime.models.schemas import ExperimentCreate, ExperimentResponse


class ExperimentService:
    def create(self, db: Session, session_id: UUID, data: ExperimentCreate) -> ExperimentResponse:
        session = db.get(SessionModel, session_id)
        if not session:
            raise NotFoundError("ERROR_SESSION_NOT_FOUND", f"Session {session_id} not found")
        experiment = Experiment(
            session_id=session_id,
            experiment_type=data.experiment_type.value,
            label=data.label,
            metadata_=data.metadata,
            status="open",
        )
        db.add(experiment)
        db.flush()
        return self._to_response(experiment)

    def get(self, db: Session, experiment_id: UUID) -> ExperimentResponse:
        experiment = db.get(Experiment, experiment_id)
        if not experiment:
            raise NotFoundError("ERROR_EXPERIMENT_NOT_FOUND", f"Experiment {experiment_id} not found")
        return self._to_response(experiment)

    @staticmethod
    def _to_response(experiment: Experiment) -> ExperimentResponse:
        return ExperimentResponse(
            experiment_id=experiment.experiment_id,
            session_id=experiment.session_id,
            experiment_type=experiment.experiment_type,
            label=experiment.label,
            status=experiment.status,
            metadata=experiment.metadata_ or {},
            started_at=experiment.started_at,
            ended_at=experiment.ended_at,
        )
