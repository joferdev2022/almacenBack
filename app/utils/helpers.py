def product_helper(products) -> dict:
    return {
        "id": str(products["_id"]),
        "nombre": products["nombre"],
        "descripcion": products["descripcion"],
        "categoria": products["categoria"],
        "precioCompra": products["precioCompra"],
        "precioVenta": products["precioVenta"],
        "cantidadEnStock": products["cantidadEnStock"],
        "unidadDeMedida": products["unidadDeMedida"],
        "proveedorId": products["proveedorId"],
        "fechaDeCaducidad": products["fechaDeCaducidad"],
        "fechaDeCreacion": products["fechaDeCreacion"],
        # "state": promotions["state"],
        "local": products["local"],
    }
    
def sale_helper(sales) -> dict:
    precio_total = sales.get("precioTotal", 0.0)
    precio_total_original = sales.get("precioTotalOriginal", precio_total)
    
    # if precio_total_original is None:
    #     precio_total_original = precio_total
    
    return {
        "id": str(sales["_id"]),
        "nombreCliente": sales["nombreCliente"],
        "fechaVenta": sales["fechaVenta"],
        "productos": sales["productos"],
        "precioTotal": float(precio_total) if precio_total is not None else 0.0,
        "precioTotalOriginal": float(precio_total_original) if precio_total_original is not None else 0.0,
        # "precioTotal": float(sales["precioTotal"]),
        # "precioTotalOriginal": float(sales.get("precioTotalOriginal", sales["precioTotal"])),
        "estado": sales["estado"],
        "local": sales["local"],
    }
    
    
