from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from events.models import Event

from .filters import EventListQuerySerializer
from .queries import event_detail_queryset, event_list_queryset
from .serializers import EventDetailSerializer, EventListSerializer


class EventPagination(PageNumberPagination):
    page_size = 50


class EventListView(generics.ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = EventListSerializer
    pagination_class = EventPagination

    @extend_schema(parameters=[EventListQuerySerializer], tags=["events"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet[Event]:
        query = EventListQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return event_list_queryset(query.validated_data)


class EventDetailView(generics.RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = EventDetailSerializer

    @extend_schema(tags=["events"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet[Event]:
        return event_detail_queryset()
