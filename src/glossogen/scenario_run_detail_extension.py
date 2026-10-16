"""The contract a scenario implements to surface its own data on the run-detail API.

A scenario returns one :class:`ScenarioRunDetailExtension` from
:meth:`glossogen.scenario_protocol.SimulationScenario.run_detail_extension`. The
server builds the ``scenario_extras`` discriminated union on ``RunDetailResponse``
from each extension's ``extras_model_cls``, and calls ``build_extras`` after the
generic event walk.

Kept out of :mod:`glossogen.server` because the scenario contract imports it.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel

from glossogen.models.event import SimulationEvent
from glossogen.run_detail_types import AgentDetail, ChannelMessage


class ScenarioRunExtrasBase(BaseModel):
    """Abstract base for the polymorphic payload attached to ``RunDetailResponse.scenario_extras``.

    Each subclass declares ``scenario_name: Literal["<name>"]`` as the
    discriminator field. Pydantic dispatches between subclasses on that field
    when validating the discriminated union.
    """


class ScenarioRunDetailExtension(ABC):
    """Per-scenario hook that materializes ``ScenarioRunExtrasBase`` from a run's event log.

    Each subclass declares the Pydantic class that holds its extras payload
    (``extras_model_cls``) and any custom SSE event classes the scenario emits
    over the live stream (``sse_event_classes``). Both are read at server
    startup to build the discriminated unions on ``RunDetailResponse`` and the
    SSE event union.
    """

    extras_model_cls: ClassVar[type[ScenarioRunExtrasBase]]
    sse_event_classes: ClassVar[tuple[type[BaseModel], ...]]

    @abstractmethod
    def build_extras(
        self,
        events: list[SimulationEvent],
        agents_by_id: dict[str, AgentDetail],
        messages: list[ChannelMessage],
    ) -> ScenarioRunExtrasBase:
        """Walk ``events`` and return the scenario-specific extras payload.

        ``agents_by_id`` and ``messages`` are the already-materialized
        platform views for the same run; extensions reuse them instead
        of re-indexing the event list.
        """
