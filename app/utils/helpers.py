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
    }
    
def sale_helper(sales) -> dict:
    return {
        "id": str(sales["_id"]),
        "nombreCliente": sales["nombreCliente"],
        "fechaVenta": sales["fechaVenta"],
        "productos": sales["productos"],
        "precioTotal": sales["precioTotal"],
        "estado": sales["estado"]
    }
    
    
