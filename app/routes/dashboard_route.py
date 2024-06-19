from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from datetime import datetime, timedelta

from app.services.dashboard_service import retrieve_dashboard_data
from app.models.dashboard_model import ResponseDashboardModel



router = APIRouter()


@router.get("/dashboard/", tags=["dashboard"])
async def get_dashboard(fecha_inicio: Optional[datetime] = Query(None), fecha_fin:  Optional[datetime] = Query(None)):
    if fecha_inicio and fecha_fin:
        filtro_fecha = {
            "fechaVenta": {
                "$gte": fecha_inicio,
                "$lt": fecha_fin
            }
        }
    else:
        fecha_fin = datetime.utcnow()
        fecha_inicio = fecha_fin - timedelta(days=30)
        filtro_fecha = {
            "fechaVenta": {
                "$gte": fecha_inicio,
                "$lt": fecha_fin
            }
        }
    
    dashboard_data = await retrieve_dashboard_data(filtro_fecha)
    
    # print(dashboard_data)
    fecha_fin_impresa = datetime.now()
    # print(fecha_fin_impresa)
    return ResponseDashboardModel(dashboard_data, "dashboard data")

