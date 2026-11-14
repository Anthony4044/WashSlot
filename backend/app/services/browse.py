"""Browse use cases: list laundromats and (later) slots by date. Public; no token."""
from app.domain.laundromat import Laundromat
from app.services.ids import LAUNDROMAT, format_id
from app.services.outcome import Outcome
from app.services.unit_of_work import UnitOfWorkFactory
from app.services.views import LaundromatDto, LaundromatListDto


def _laundromat_dto(lm: Laundromat) -> LaundromatDto:
    return LaundromatDto(
        laundromat_id=format_id(LAUNDROMAT, lm.id),
        name=lm.name,
        address=lm.address,
        timezone=lm.timezone,
    )


class BrowseService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self.uow_factory = uow_factory

    def list_laundromats(self) -> Outcome:
        """GET /laundromats — every laundromat, by name."""
        with self.uow_factory() as uow:
            rows = uow.laundromats.list_all()
        return Outcome.success(LaundromatListDto(laundromats=[_laundromat_dto(lm) for lm in rows]))
