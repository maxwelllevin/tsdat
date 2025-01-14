import warnings
from typing import Any, Dict, Optional

from pydantic import (
    BaseModel,
    Extra,
    Field,
    HttpUrl,
    StrictStr,
    root_validator,
    validator,
)
from pydantic.fields import ModelField

from ..utils import get_datastream
from .utils import get_code_version


class AttributeModel(BaseModel, extra=Extra.allow):
    # HACK: root is needed for now: https://github.com/samuelcolvin/pydantic/issues/515
    @root_validator(skip_on_failure=True)
    @classmethod
    def validate_all_ascii(cls, values: Dict[Any, Any]) -> Dict[str, str]:
        for key, value in values.items():
            if not isinstance(key, str) or not key.isascii():
                raise ValueError(f"'{key}' contains a non-ascii character.")
            if isinstance(value, str) and not value.isascii():
                raise ValueError(
                    f"attr '{key}' -> '{value}' contains a non-ascii character."
                )
        return values


class GlobalAttributes(AttributeModel):
    """Global attributes that will be recorded in the output dataset. These metadata are
    used to record data provenance information (e.g., location, institution, etc),
    construct datastream and file names (i.e., location_id, dataset_name, qualifier,
    temporal, and data_level attributes), as well as provide metadata that is useful for
    data users (e.g., title, description, ... ).
    """

    title: str = Field(
        min_length=1,
        description=(
            "A succinct description of the dataset. This value may be similar to a"
            " publication title and should be suitable for use as a title in plots or"
            " other references to this dataset."
        ),
    )
    description: str = Field(
        min_length=1,
        description=(
            "A user-friendly description of the dataset. It should provide"
            " enough context about the data for new users to quickly understand how the"
            " data can be used."
        ),
    )
    code_url: Optional[HttpUrl] = Field(
        default=None, description="Where the code is hosted."
    )
    conventions: Optional[StrictStr] = Field(
        default=None, description="The data conventions the dataset follows."
    )
    doi: Optional[StrictStr] = Field(
        default=None,
        description="The DOI that has been registered for this dataset, if applicable.",
    )
    institution: Optional[StrictStr] = Field(
        default=None,
        description=(
            "The institution or organization that produces or manages this data."
        ),
    )
    references: Optional[StrictStr] = Field(
        default=None,
        description=(
            "Optional attribute used to cite other data, algorithms, etc. as needed."
        ),
    )
    location_id: str = Field(
        min_length=1,
        regex=r"^[a-zA-Z0-9_]+$",  # alphanumeric and '_' characters
        description=(
            "A label or acronym for the location where the data were obtained"
            " from. Only alphanumeric characters and '_' are allowed."
        ),
    )
    dataset_name: str = Field(
        min_length=2,
        regex=r"^[a-z0-9_]+$",  # lowercase alphanumeric and '_' characters
        description=(
            "A string used to identify the data being produced. Ideally"
            " resembles a shortened lowercase version of the title. Only lowercase"
            " alphanumeric characters and '_' are allowed."
        ),
    )
    qualifier: Optional[str] = Field(
        default=None,
        min_length=1,
        regex=r"^[a-zA-Z0-9_]+$",  # lowercase alphanumeric and '_' characters
        description=(
            "An optional string which distinguishes these data from other"
            " datasets produced by the same instrument. Only alphanumeric characters"
            " and '_' are allowed."
        ),
    )
    temporal: Optional[str] = Field(
        default=None,
        min_length=2,
        regex=r"^[0-9]+[a-zA-Z]+$",
        description=(
            "An optional string which describes the temporal resolution of the data (if"
            " spaced in regular intervals). This string should be formatted as a number"
            " followed by a unit of measurement, e.g., '10m' would indicate the data is"
            " sampled every ten minutes. Only lowercase alphanumeric characters are"
            " allowed."
        ),
    )
    data_level: str = Field(
        min_length=2,
        max_length=3,
        regex=r"^[a-z0-9]+$",  # lowercase alphanumeric characters
        description=(
            "A string used to indicate the level of processing of the output data. It"
            " should be formatted as a letter followed by a number. Typical values for"
            " this include: a1 - data is ingested (no qc), b1 - data is ingested and"
            " quality checks applied, c1 (or higher) - one or more a* or b* datastreams"
            " used to create a higher-level data product. Only lowercase alphanumeric"
            " characters are allowed."
        ),
    )

    # Autogenerated attributes:
    datastream: StrictStr = Field(
        "",
        description=(
            "Typically used as a label that uniquely identifies this data product from"
            " any other data product. For file-based storage systems, the datastream"
            " attribute is typically used to generate directory structures as"
            " f'{location_id}/{datastream}/', with files in that directory typically"
            " named as f'{datastream}.{date}.{time}.{ext}'. This attribute is"
            " AUTO-GENERATED at run-time, unless it is explicitly set in the config"
            " file, in which case the value in the config file will override the"
            " default. The default value for 'datastream' is as follows:\n"
            ' f"{location_id}.{dataset_name}{_qualifier}{_temporal}.{data_level}",'
            " \nwhere '_qualifier' and '_temporal' are both prepended with a literal"
            " '-' character if they are provided. This gives some separation between"
            " the 'dataset_name', 'qualifier', and 'temporal' attributes and makes it"
            " possible to parse out these specific attributes given a complete"
            " datastream label."
        ),
    )
    history: StrictStr = Field(
        "",
        description=(
            "Attribute that will be recorded automatically by the pipeline. A"
            " warning will be raised if this is set in the config file."
        ),
    )
    code_version: StrictStr = Field(
        default_factory=get_code_version,
        description=(
            "Attribute that will be recorded automatically by the pipeline. A warning"
            " will be raised if this is set in the config file. The code_version"
            " attribute reads the 'CODE_VERSION' environment variable or parses the git"
            " history to determine the version of the code. Semantic versioning is used"
            " by default (v'major.minor.micro'; e.g., 1.2.3)."
        ),
    )

    @validator("history", "code_version", pre=True)
    @classmethod
    def warn_if_dynamic_properties_are_set(cls, v: str, field: ModelField) -> str:
        if v:
            warnings.warn(
                f"The '{field.name}' attribute should not be set explicitly. The"
                f" current value of '{v}' will be ignored."
            )
        return ""

    @root_validator(skip_on_failure=True)
    @classmethod
    def add_datastream_field(cls, values: Dict[str, StrictStr]) -> Dict[str, StrictStr]:
        if not values["datastream"]:
            values["datastream"] = get_datastream(**values)
        return values
