from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('bookings', '0002_contrato_contratoversion_historialestadoreserva_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                'ALTER TABLE solicitud_cancelacion '
                'ALTER COLUMN rut_titular TYPE VARCHAR(30)'
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql=(
                'ALTER TABLE solicitud_cancelacion '
                'ADD COLUMN IF NOT EXISTS tipo_documento_titular VARCHAR(20)'
            ),
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
