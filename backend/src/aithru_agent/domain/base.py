from pydantic import BaseModel, ConfigDict


class AithruBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

