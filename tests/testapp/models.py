from django.db import models
from django.utils import timezone


class ItemMovement(models.Model):
    entered = models.DateTimeField(default=timezone.now)
    left = models.DateTimeField(null=True, blank=True)
    item = models.ForeignKey('Item')
    container = models.ForeignKey('Container')


class Item(models.Model):
    name = models.CharField(max_length=100)

    def current_container(self):
        current_container = [
            through.container for through in self.itemmovement_set.all()
            if through.left is None
        ]
        if not current_container:
            return None
        assert len(current_container) == 1
        return current_container[0]


class Container(models.Model):
    name = models.CharField(max_length=100, unique=True)
    items = models.ManyToManyField(
        Item,
        through=ItemMovement,
        related_name='containers')
