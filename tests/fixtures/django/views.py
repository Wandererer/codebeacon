from django.http import JsonResponse
from django.views import View
from django.db import models


class User(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)

    class Meta:
        db_table = "users"


class UserListView(View):
    def get(self, request):
        users = list(User.objects.values())
        return JsonResponse(users, safe=False)

    def post(self, request):
        import json
        data = json.loads(request.body)
        user = User.objects.create(**data)
        return JsonResponse({"id": user.id})


class UserDetailView(View):
    def get(self, request, pk):
        user = User.objects.get(pk=pk)
        return JsonResponse({"id": user.id, "name": user.name})

    def put(self, request, pk):
        import json
        data = json.loads(request.body)
        User.objects.filter(pk=pk).update(**data)
        return JsonResponse({"updated": pk})

    def delete(self, request, pk):
        User.objects.filter(pk=pk).delete()
        return JsonResponse({"deleted": pk})
