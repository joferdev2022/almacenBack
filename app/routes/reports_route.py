from datetime import date, datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.services import reports_service as service
from app.services.expenses_service import get_expense_user as get_current_user
from app.utils.cash_helpers import LIMA

router = APIRouter(prefix="/reports", tags=["reports"])


def get_report_user(local: Optional[int] = None, user: dict = Depends(get_current_user)):
    if user.get("permissions") != 1:
        raise HTTPException(403, "No tienes permiso para consultar reportes y precios de compra.")
    if local is not None and local != user["local"]:
        raise HTTPException(403, "No puedes consultar reportes de otro local.")
    return user


def report_filters(fecha_desde: Optional[date] = None, fecha_hasta: Optional[date] = None,
                   producto: str = Query("", max_length=120), categoria: str = Query("", max_length=200),
                   ventas: Literal["todas", "pagadas"] = "todas"):
    today = datetime.now(LIMA).date()
    return service.ReportFilters(fecha_desde or today.replace(month=1, day=1), fecha_hasta or today,
                                 producto.strip(), categoria.strip(), ventas)


@router.get("/sales")
def sales(response: Response, page: int = Query(1, ge=1), xpage: int = Query(25, ge=1, le=100),
          filters: service.ReportFilters = Depends(report_filters), user: dict = Depends(get_report_user)):
    report = service.build_report(user, filters)
    report["filas"] = report["filas"][(page - 1) * xpage:page * xpage]
    report.update(page=page, xpage=xpage)
    response.headers["Cache-Control"] = "no-store"
    return {"data": report, "code": 200, "message": "Reporte mensual de ventas"}


@router.get("/sales/excel")
def sales_excel(filters: service.ReportFilters = Depends(report_filters), user: dict = Depends(get_report_user)):
    report = service.build_report(user, filters, for_export=True)
    content = service.export_excel(report)
    filename = f"ventas_local_{user['local']}_{filters.fecha_desde}_{filters.fecha_hasta}.xlsx"
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})
