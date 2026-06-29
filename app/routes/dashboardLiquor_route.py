from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from datetime import datetime, timedelta
import calendar

from app.services.dashboardLiquor_service import retrieve_dashboard_data
from app.models.dashboardLiquor_model import ResponseDashboardModel



router = APIRouter()


@router.get("/dashboardliquor/", tags=["liquor dashboard"])
async def get_dashboard(fecha_inicio: Optional[datetime] = Query(None), fecha_fin:  Optional[datetime] = Query(None), local: int = Query(1)):
    if fecha_inicio and fecha_fin:
        filtro_fecha = {
            "fechaVenta": {
                "$gte": fecha_inicio,
                "$lt": fecha_fin
            }
        }
    else:
        hoy = datetime.utcnow()
        primer_dia_mes = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # fecha_fin = datetime.utcnow()
        # fecha_inicio = fecha_fin - timedelta(days=30)
                # Obtener el primer día del próximo mes
        if hoy.month == 12:
            ultimo_dia_mes = hoy.replace(year=hoy.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            ultimo_dia_mes = hoy.replace(month=hoy.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
     
        filtro_fecha = {
            "fechaVenta": {
                "$gte": primer_dia_mes,
                "$lt": ultimo_dia_mes
            }
        }
    
    dashboard_data = await retrieve_dashboard_data(filtro_fecha, local)
    
    # print(dashboard_data)
    fecha_fin_impresa = datetime.now()
    # print(fecha_fin_impresa)
    return ResponseDashboardModel(dashboard_data, "dashboard data")

