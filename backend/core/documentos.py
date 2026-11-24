"""Generación de PDFs de reserva, contrato y consentimiento."""

import re
import textwrap
from datetime import datetime
from decimal import Decimal

from django.utils import timezone


ANCHO_PAGINA = 612
ALTO_PAGINA = 792


def _literal_pdf(texto):
    """Codifica texto con WinAnsi y escapa los caracteres de cadenas PDF."""
    resultado = bytearray(b'(')
    for byte in str(texto).encode('cp1252', errors='replace'):
        if byte in (40, 41, 92):
            resultado.extend(b'\\' + bytes((byte,)))
        elif byte < 32 or byte > 126:
            resultado.extend(f'\\{byte:03o}'.encode('ascii'))
        else:
            resultado.append(byte)
    resultado.extend(b')')
    return bytes(resultado)


def _texto_pdf(texto, x, y, tamano=10, fuente='F1', color='0.16 0.20 0.23'):
    comando = (
        f'{color} rg BT /{fuente} {tamano} Tf {x} {y} Td '.encode('ascii')
        + _literal_pdf(texto)
        + b' Tj ET\n'
    )
    return comando


def _es_encabezado(linea):
    linea = linea.strip()
    if not linea or ':' in linea or len(linea) > 68:
        return False
    return bool(re.match(r'^\d+\.\s+', linea)) or (
        linea == linea.upper() and any(caracter.isalpha() for caracter in linea)
    )


def _texto_envuelto(linea, ancho=96):
    linea = linea.strip()
    if not linea:
        return ['']
    return textwrap.wrap(
        linea,
        width=ancho,
        break_long_words=False,
        break_on_hyphens=False,
        subsequent_indent='   ',
    ) or ['']


def _construir_pdf(contenidos):
    cantidad_paginas = len(contenidos)
    id_fuente_regular = 3 + cantidad_paginas * 2
    id_fuente_negrita = id_fuente_regular + 1
    objetos = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        (
            f'<< /Type /Pages /Kids ['
            f'{" ".join(str(3 + indice * 2) + " 0 R" for indice in range(cantidad_paginas))}'
            f'] /Count {cantidad_paginas} >>'
        ).encode('ascii'),
    ]

    for indice, contenido in enumerate(contenidos):
        id_pagina = 3 + indice * 2
        id_contenido = id_pagina + 1
        objetos.append(
            f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {ANCHO_PAGINA} {ALTO_PAGINA}] '
            f'/Resources << /Font << /F1 {id_fuente_regular} 0 R '
            f'/F2 {id_fuente_negrita} 0 R >> >> /Contents {id_contenido} 0 R >>'
            .encode('ascii')
        )
        objetos.append(
            f'<< /Length {len(contenido)} >>\nstream\n'.encode('ascii')
            + contenido
            + b'endstream'
        )

    objetos.extend((
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>',
    ))

    pdf = bytearray(b'%PDF-1.4\n')
    offsets = [0]
    for numero, objeto in enumerate(objetos, 1):
        offsets.append(len(pdf))
        pdf.extend(f'{numero} 0 obj\n'.encode('ascii'))
        pdf.extend(objeto)
        pdf.extend(b'\nendobj\n')

    inicio_xref = len(pdf)
    pdf.extend(f'xref\n0 {len(objetos) + 1}\n'.encode('ascii'))
    pdf.extend(b'0000000000 65535 f \n')
    for offset in offsets[1:]:
        pdf.extend(f'{offset:010d} 00000 n \n'.encode('ascii'))
    pdf.extend(
        f'trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n'
        f'startxref\n{inicio_xref}\n%%EOF'.encode('ascii')
    )
    return bytes(pdf)


def pdf_desde_lineas(lineas, max_lineas_por_pagina=44):
    """Construye un PDF con encabezados, secciones y pie de página."""
    lineas = [str(linea) for linea in lineas]
    titulo = lineas[0].strip() if lineas else 'Documento de reserva'
    codigo = next(
        (
            linea.partition(':')[2].strip()
            for linea in lineas
            if linea.lower().startswith(('código de reserva:', 'codigo de reserva:'))
        ),
        'Documento asociado a una reserva',
    )
    paginas = []
    operaciones = []
    y = 0

    def nueva_pagina():
        nonlocal operaciones, y
        operaciones = [
            b'q\n0.12 0.18 0.22 rg\n0 680 612 112 re f\nQ\n',
            _texto_pdf('RENTACAR', 48, 754, 10, 'F2', '1 1 1'),
            _texto_pdf(titulo, 48, 718, 20, 'F2', '1 1 1'),
            _texto_pdf(f'Reserva {codigo}', 48, 696, 9, 'F1', '0.82 0.88 0.87'),
            b'0.25 0.66 0.58 rg 48 680 48 3 re f\n',
        ]
        y = 650

    def agregar_texto(texto, tamano=10, fuente='F1', color='0.16 0.20 0.23', alto=15):
        nonlocal y
        if y - alto < 74:
            paginas.append(operaciones)
            nueva_pagina()
        operaciones.append(_texto_pdf(texto, 52, y, tamano, fuente, color))
        y -= alto

    nueva_pagina()
    lineas_cuerpo = lineas[1:]
    for linea in lineas_cuerpo:
        if not linea.strip():
            y -= 6
            continue
        if _es_encabezado(linea):
            if y < 102:
                paginas.append(operaciones)
                nueva_pagina()
            y -= 3
            agregar_texto(linea.strip(), 11, 'F2', '0.12 0.36 0.34', 18)
            operaciones.append(b'0.82 0.87 0.86 RG 52 ' + str(y + 5).encode('ascii') + b' m 560 '
                               + str(y + 5).encode('ascii') + b' l 0.6 w S\n')
            y -= 3
            continue
        for linea_envuelta in _texto_envuelto(linea):
            agregar_texto(linea_envuelta)

    paginas.append(operaciones)
    cantidad_paginas = len(paginas)
    contenidos = []
    for indice, pagina in enumerate(paginas, 1):
        pagina.append(b'0.84 0.87 0.86 RG 48 57 m 564 57 l 0.6 w S\n')
        pagina.append(_texto_pdf(
            f'Rentacar · Reserva {codigo} · Documento informativo',
            48, 40, 8, 'F1', '0.38 0.43 0.45',
        ))
        pagina.append(_texto_pdf(
            f'Página {indice} de {cantidad_paginas}',
            476, 40, 8, 'F1', '0.38 0.43 0.45',
        ))
        contenidos.append(b''.join(pagina))
    return _construir_pdf(contenidos)


def fecha_documento(valor):
    if not valor:
        return 'No disponible'
    if isinstance(valor, str):
        try:
            valor = datetime.fromisoformat(valor.replace('Z', '+00:00'))
        except ValueError:
            return valor
    if timezone.is_aware(valor):
        valor = timezone.localtime(valor)
    return valor.strftime('%d/%m/%Y %H:%M')


def pesos_documento(valor):
    try:
        monto = int(Decimal(str(valor)))
    except (ValueError, TypeError, ArithmeticError):
        return str(valor or '0')
    return f'${monto:,}'.replace(',', '.')


def _documento_cliente(cliente):
    tipo = cliente.get('tipo_documento') or 'Documento'
    tipo = {'RUT': 'RUT', 'PASAPORTE': 'Pasaporte'}.get(tipo, tipo.replace('_', ' ').title())
    numero = cliente.get('documento') or 'Por verificar en sucursal'
    return f'{tipo}: {numero}'


def contrato_lineas(info):
    """Cuerpo del contrato aceptado para una reserva."""
    cliente = info['cliente']
    fecha_aceptacion = fecha_documento(info.get('fecha_firma'))
    medio = info.get('medio_aceptacion') or 'No disponible'
    return [
        'CONTRATO DE ARRIENDO',
        f'Código de reserva: {info.get("codigo") or info["codigo_reserva"]}',
        f'Fecha de aceptación: {fecha_aceptacion}',
        f'Medio de aceptación: {medio}',
        f'Versión del contrato: {info.get("version_contrato") or "No disponible"}',
        '',
        '1. PARTES',
        f'   ARRENDADOR: Rentacar, sucursal {info["sucursal_retiro"]}.',
        f'   ARRENDATARIO: {cliente["nombre"]} {cliente["apellido"]}.',
        f'   Documento del arrendatario: {_documento_cliente(cliente)}',
        f'   Correo: {cliente["email"]}  Teléfono: {cliente.get("telefono") or "No informado"}',
        '',
        '2. VEHÍCULO',
        f'   Vehículo {info["vehiculo"]}, patente {info["patente"]}, categoría {info["categoria"]}.',
        '',
        '3. PLAZO Y SUCURSAL',
        f'   Retiro: {fecha_documento(info["fecha_hora_retiro"])} · {info["sucursal_retiro"]}.',
        f'   Devolución: {fecha_documento(info["fecha_hora_devolucion"])} · {info["sucursal_devolucion"]}.',
        '   El vehículo debe devolverse en la sucursal y horario pactados.',
        '',
        '4. PRECIO Y GARANTÍA',
        f'   Total pagado por el arriendo: {pesos_documento(info["total_pagado"])}.',
        f'   Garantía a presentar en sucursal: {pesos_documento(info["garantia_monto"])}.',
        '   La garantía se presenta al retirar el vehículo, conforme a lo informado',
        '   antes de reservar. La empresa no almacena datos de tarjetas de pago.',
        '',
        '5. OBLIGACIONES DEL ARRENDATARIO',
        '   a) Presentar documento de identidad y licencia de conducir vigente.',
        '   b) Usar el vehículo conforme a la ley y al manual del fabricante.',
        '   c) No utilizar el vehículo para transporte remunerado ni competencias.',
        '   d) Devolver el vehículo con el nivel de combustible acordado.',
        '',
        '6. CANCELACIÓN Y DEVOLUCIÓN',
        '   El retracto solicitado dentro de 10 días desde la reserva y antes de iniciar',
        '   el servicio se cotiza con devolución total.',
        '   En otros casos, con más de 48 horas se devuelve el total; entre 24 y 48 horas',
        '   se retiene un día de tarifa; con menos de 24 horas, dos días; no-show, tres días.',
        '   La retención no supera el monto pagado. Las solicitudes se revisan manualmente',
        '   y Finanzas ejecuta por transferencia las devoluciones aprobadas.',
        '',
        '7. CONSTANCIA DE ACEPTACIÓN',
        (
            f'   Aceptación electrónica registrada el {fecha_aceptacion}.'
            if info.get('fecha_firma')
            else '   No hay constancia de aceptación asociada a esta reserva.'
        ),
        f'   Dirección IP registrada: {info.get("ip_cliente") or "No disponible"}.',
    ]


def consentimiento_lineas(info):
    """Cuerpo del consentimiento informado asociado a la reserva."""
    cliente = info['cliente']
    fecha_aceptacion = fecha_documento(info.get('fecha_firma'))
    return [
        'CONSENTIMIENTO INFORMADO',
        f'Código de reserva: {info.get("codigo") or info["codigo_reserva"]}',
        f'Fecha de aceptación: {fecha_aceptacion}',
        '',
        'DECLARACIÓN DEL CLIENTE',
        f'Yo, {cliente["nombre"]} {cliente["apellido"]},',
        f'{_documento_cliente(cliente)}, declaro que:',
        '',
        '1. Los datos entregados para la reserva son verdaderos, completos y vigentes.',
        '2. Tengo al menos 18 años y cuento con licencia de conducir vigente.',
        '3. Acepto que mi identidad y licencia sean verificadas en la sucursal al retirar',
        '   el vehículo.',
        '4. Autorizo el tratamiento de mis datos personales para gestionar la reserva,',
        '   el pago, la entrega del vehículo y responder solicitudes, conforme a la',
        '   normativa de protección de datos personales aplicable.',
        '5. He leído y acepto el contrato de arriendo asociado a esta reserva.',
        '6. Sé que la garantía se presenta en la sucursal según las condiciones informadas',
        '   y que la empresa no almacena datos de tarjetas de pago.',
        '',
        'REGISTRO',
        f'   Aceptación: {fecha_aceptacion}.',
        f'   Medio: {info.get("medio_aceptacion") or "No disponible"}.',
        '   Este documento acompaña al contrato y al comprobante de reserva.',
    ]
