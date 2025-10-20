from django.db import models

class Device(models.Model):
    name = models.CharField(max_length=200)
    serial_number = models.CharField(max_length=100, unique=True)
    device_type = models.CharField(max_length=100) # Принтер, Сканер, ПК и т.д.
    status = models.CharField(max_length=50, default='active') # active, in_repair, retired
    location = models.CharField(max_length=200, blank=True)
    # ... другие поля
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Log(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='logs')
    error_message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    # ... другие поля

    class Meta:
        ordering = ['-timestamp'] # Сортировка по убыванию времени

# ... другие модели (например, Request для заявок)
