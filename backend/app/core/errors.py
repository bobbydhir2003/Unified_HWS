from fastapi import HTTPException, status


def not_found(what: str = "Resource") -> HTTPException:
    # 404 (not 403) for cross-tenant ids so existence is not leaked.
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


def forbidden(msg: str = "You do not have permission to perform this action") -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, msg)


def conflict(msg: str, **extra) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, {"message": msg, **extra} if extra else msg)


def bad_request(msg: str) -> HTTPException:
    return HTTPException(status.HTTP_400_BAD_REQUEST, msg)
