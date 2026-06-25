"""Pydantic AI capability wrapping an Aithru SkillPackage for deferred/explicit loading."""

from dataclasses import dataclass

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.models import ModelRequestContext

from aithru_agent.agent.deps import PydanticAgentDeps
from aithru_agent.agent.skill_policy import active_skill_keys
from aithru_agent.skills.packages import SkillPackage


def skill_capability_id(key: str) -> str:
    return f"skill:{key}"


@dataclass
class AithruSkillCapability(AbstractCapability[PydanticAgentDeps]):
    """Expose an Aithru Skill Package as a Pydantic AI capability.

    When `explicit` is True (the user selected the skill for this run), the
    capability loads on the first model request. Otherwise it is deferred:
    the model sees only the id and description and may load it via
    Pydantic AI's framework-managed `load_capability` tool.
    """

    package: SkillPackage
    explicit: bool = False

    def __post_init__(self) -> None:
        self.id = skill_capability_id(self.package.key)
        self.description = self.package.discovery_description
        self.defer_loading = not self.explicit

    def get_instructions(self) -> str:
        return "\n\n".join(
            [
                f"## Aithru Skill: {self.package.metadata.name}",
                self.package.instructions,
            ]
        )


@dataclass
class AithruSkillActivationObserver(AbstractCapability[PydanticAgentDeps]):
    """Emit skill.activated events when skills are loaded by the runtime.

    Tracks already-emitted keys to avoid duplicate events across
    repeated model requests within the same run.
    """

    def __post_init__(self) -> None:
        self.id = "aithru-skill-activation-observer"
        self.defer_loading = False

    async def before_model_request(
        self,
        ctx: RunContext[PydanticAgentDeps],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        active = active_skill_keys(ctx)
        already_emitted = ctx.deps.emitted_skill_activation_keys
        for key in active:
            if key in already_emitted:
                continue
            package = ctx.deps.visible_skill_packages.get(key)
            if package is None:
                continue
            await ctx.deps.event_writer.write(
                run_id=ctx.deps.run.id,
                thread_id=ctx.deps.run.thread_id,
                type="skill.activated",
                source={"kind": "harness"},
                visibility="debug",
                payload={
                    "skill_key": key,
                    "source": package.source,
                    "owner_user_id": package.owner_user_id,
                    "trigger": "explicit" if key == ctx.deps.explicit_skill_key else "pydantic_load_capability",
                    "policy": {
                        "allowed_tools": package.policy.allowed_tools,
                        "denied_tools": package.policy.denied_tools,
                    },
                },
            )
            already_emitted.add(key)
        return request_context
