from pydantic import BaseModel, Field, field_validator
import re

# This defines what a valid Login Request looks like
class LoginRequest(BaseModel):
    # Field(...) means "Required"
    username: str = Field(..., max_length=12, min_length=1)

    # Custom validator to check for special characters
    @field_validator('username')
    @classmethod
    def validate_alphanumeric(cls, v):
        if not re.match("^[a-zA-Z0-9]+$", v):
            raise ValueError('Username must contain only letters and numbers')
        return v

# This defines what a valid Guess Request looks like
class GuessRequest(BaseModel):
    guess: int = Field(..., ge=1) # ge=1 means "greater than or equal to 1"