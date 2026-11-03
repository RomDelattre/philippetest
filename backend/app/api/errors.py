from fastapi import HTTPException, status


def check_version(current: int, expected: int) -> None:
    """R-12 : l'écriture porte la version lue ; sinon 409 et le front recharge."""
    if current != expected:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Donnée modifiée par un autre utilisateur, rechargez la page.",
        )


def not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} introuvable")


def unprocessable(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def precondition(code: str, message: str) -> HTTPException:
    """428 : l'action demande une confirmation explicite. `code` indique laquelle au front :
    confirm_sent (F-07, F-26), dates_differ (R-03), conflict (R-02)."""
    return HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, {"code": code, "message": message})
