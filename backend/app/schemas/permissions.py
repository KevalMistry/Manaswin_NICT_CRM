from pydantic import BaseModel, Field


class ModulePermission(BaseModel):
    module_key: str
    label: str
    can_access: bool


class RolePermissionResponse(BaseModel):
    role_id: int
    role_name: str
    branch_id: int | None = None
    branch_name: str | None = None
    can_edit: bool = True
    permissions: list[ModulePermission]


class PermissionUpdate(BaseModel):
    permissions: dict[str, bool] = Field(min_length=1)


class MyPermissionsResponse(BaseModel):
    role_name: str
    role_id: int
    branch_id: int | None = None
    branch_name: str | None = None
    can_manage_permissions: bool
    allowed_modules: list[str]
