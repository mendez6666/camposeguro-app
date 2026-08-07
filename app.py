<p>Revisa el correo y la clave.</p><a class='btn primary' href='/login'>Volver</a></div>"
        return layout("Acceso", body, None)
    request.session["user_id"] = int(user["id"])
    if user["role"] == "admin":
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/cliente", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


def counts_for(user_id: int | None = None) -> dict[str, int]:
    if user_id:
        users = 1
        zones = db.execute("SELECT COUNT(*) AS n FROM zones WHERE user_id=%s AND active=TRUE", (user_id,), fetch="one")["n"]
        alerts = db.execute("SELECT COUNT(*) AS n FROM zone_alerts WHERE user_id=%s AND active=TRUE", (user_id,), fetch="one")["n"]
        critical = db.execute("SELECT COUNT(*) AS n FROM zone_alerts WHERE user_id=%s AND active=TRUE AND level='CRITICO'", (user_id,), fetch="one")["n"]
    else:
        users = db.execute("SELECT COUNT(*) AS n FROM users WHERE active=TRUE AND role='client'", fetch="one")["n"]
        zones = db.execute("SELECT COUNT(*) AS n FROM zones WHERE active=TRUE", fetch="one")["n"]
        alerts = db.execute("SELECT COUNT(*) AS n FROM zone_alerts WHERE active=TRUE", fetch="one")["n"]
        critical = db.execute("SELECT COUNT(*) AS n FROM zone_alerts WHERE active=TRUE AND level='CRITICO'", fetch="one")["n"]
    focos = db.execute("SELECT COUNT(*) AS n FROM focos", fetch="one")["n"]
    return {"users": int(users), "zones": int(zones), "focos": int(focos), "alerts": int(alerts), "critical": int(critical)}


def stats_grid(stats: dict[str, int], client: bool = False) -> str:
    labels = [
        ("Usuarios activos" if not client else "Mis zonas monitoreadas", stats["users"] if not client else stats["zones"]),
        ("Zonas activas" if not client else "Focos asociados", stats["zones"] if not client else stats["focos"]),
        ("Focos FIRMS" if not client else "Zonas con alerta", stats["focos"] if not client else stats["alerts"]),
        ("Zonas con alerta" if not client else "Críticas", stats["alerts"] if not client else stats["critical"]),
        ("Críticas", stats["critical"]),
