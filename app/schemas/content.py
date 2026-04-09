from pydantic import BaseModel, ConfigDict


class ContentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    audience: str
