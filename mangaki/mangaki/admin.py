# coding=utf8
from mangaki.models import Work, TaggedWork, WorkTitle, Language, Genre, Track, Tag, Artist, Studio, Editor, Rating, Page, Suggestion, SearchIssue, Announcement, Recommendation, Pairing, Reference, Top, Ranking, Role, Staff
from django.contrib import admin
from django.template.response import TemplateResponse
from django.contrib.admin import helpers
from django.core.urlresolvers import reverse
from django.conf.urls import patterns

from django.core.management.base import BaseCommand, CommandError
from mangaki.utils.anidb import AniDB
from mangaki.models import Artist, Tag, TaggedWork, Role, Staff, Work, WorkTitle, ArtistSpelling
from django.db.models import Count
from urllib.parse import urlparse, parse_qs
import sys


class TagAdmin(admin.ModelAdmin):
    list_display = ("title", )
    readonly_fields = ("nb_works_linked",)
    
    def get_queryset(self, request):
        qs = super(TagAdmin, self).get_queryset(request)
        return qs.annotate(works_linked=Count('work'))

    def nb_works_linked(self, obj):
      return obj.works_linked
    nb_works_linked.short_description = 'Number of works linked'
    

class TaggedWorkAdmin(admin.ModelAdmin):
    search_fields = ('work', 'tag')


class TaggedWorkInline(admin.TabularInline):
    model = TaggedWork
    fields = ('work', 'tag', 'weight')


class StaffInline(admin.TabularInline):
    model = Staff
    fields = ('role', 'artist')


class WorkTitleInline(admin.TabularInline):
    model = WorkTitle
    fields = ('title', 'language','type')


class AniDBaidListFilter(admin.SimpleListFilter):
    title = (' having an AniDB aid')
    parameter_name = 'having an AniDB aid'

    def lookups(self, request, model_admin):
        return (('True', ('Oui')), ('False', ('Non')))

    def queryset(self, request, queryset):
        if self.value() == 'False':
            return queryset.filter(anidb_aid=0)
        else :
            return queryset.exclude(anidb_aid =0)


class WorkAdmin(admin.ModelAdmin):
    search_fields = ('id', 'title')
    list_display = ('id', 'title', 'nsfw')
    list_filter = ('category', 'nsfw', AniDBaidListFilter, )
    actions = ['make_nsfw', 'make_sfw', 'merge', 'anidb']
    inlines = [StaffInline, WorkTitleInline, TaggedWorkInline]
    readonly_fields = (
        'sum_ratings',
        'nb_ratings',
        'nb_likes',
        'nb_dislikes',
        'controversy',
    )

    def make_nsfw(self, request, queryset):
        rows_updated = queryset.update(nsfw=True)
        if rows_updated == 1:
            message_bit = "1 œuvre est"
        else:
            message_bit = "%s œuvres sont" % rows_updated
        self.message_user(request, "%s désormais NSFW." % message_bit)
    make_nsfw.short_description = "Rendre NSFW les œuvres sélectionnées"

    #update_tags_via_anidb
    def anidb(self, request, queryset):
        
        if request.POST.get("post"):
            
            chosen_ids = request.POST.getlist('checks')
            for anime_id in chosen_ids:
                anime = Work.objects.get(id=anime_id)
                a = AniDB('mangakihttp', 1)
                retrieve_tags = anime.retrieve_tags(a)
                deleted_tags = retrieve_tags["deleted_tags"]
                added_tags = retrieve_tags["added_tags"]
                updated_tags = retrieve_tags["updated_tags"]

                for  title, weight in added_tags.items():
                    current_tag = Tag.objects.get_or_create(title=title)[0]
                    TaggedWork(tag=current_tag, work=anime, weight=weight).save()

                
                tags = Tag.objects.filter(title__in=updated_tags.keys())
                for tag in tags:
                    tagged_work = anime.taggedwork_set.objects.get(tag=tag)
                    tagged_work.weight = updated_tags[tag.title]
                    tagged_work.save()
                
                TaggedWork.objects.filter(work=anime, tag__title__in=deleted_tags.keys()).delete()
                
            self.message_user(request, "Modifications sur les tags faites")
            return None
        
        for anime in queryset.select_related("category"):
            if anime.category.slug != 'anime':
                self.message_user(request, "%s n'est pas un anime. La recherche des tags via AniDB n'est possible que pour les animes " %anime.title)
                self.message_user(request, "Vous avez un filtre à votre droite pour avoir les animes avec un anidb_aid")
                return None
            elif not anime.anidb_aid:
                self.message_user(request, "%s n'a pas de lien actuel avec la base d'aniDB (pas d'anidb_aid)" %anime.title)
                self.message_user(request, "Vous avez un filtre à votre droite pour avoir les animes avec un anidb_aid")
                return None
            

        all_information={}
        for anime in queryset :
            a = AniDB('mangakihttp', 1)
            retrieve_tags = anime.retrieve_tags(a)
            deleted_tags = retrieve_tags["deleted_tags"]
            added_tags = retrieve_tags["added_tags"]
            updated_tags = retrieve_tags["updated_tags"]
            kept_tags = retrieve_tags["kept_tags"]
            all_information[anime.id] = [anime.title, deleted_tags.items(), added_tags.items(), updated_tags.items(), kept_tags.items()] #ou bien deleted_tags=[deleted_tags_obj1, ....]

        context = {
        'all_information' : all_information.items(),
        'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
        }
        return TemplateResponse(request, "test.html", context)
    anidb.short_description = "Mise à jour des tags des oeuvres sélectionnées" 

    def make_sfw(self, request, queryset):
        rows_updated = queryset.update(nsfw=False)
        if rows_updated == 1:
            message_bit = "1 œuvre n'est"
        else:
            message_bit = "%s œuvres ne sont" % rows_updated
        self.message_user(request, "%s désormais plus NSFW." % message_bit)
    make_sfw.short_description = "Rendre SFW les œuvres sélectionnées"

    def merge(self, request, queryset):
        queryset = queryset.order_by('id')
        if request.POST.get('post'):
            chosen_id = int(request.POST.get('chosen_id'))
            for obj in queryset:
                if obj.id != chosen_id:
                    for rating in Rating.objects.filter(work=obj).select_related('user'):
                        # S'il n'a pas déjà voté pour l'autre
                        if Rating.objects.filter(user=rating.user, work__id=chosen_id).count() == 0:
                            rating.work_id = chosen_id
                            rating.save()
                        else:
                            rating.delete()
                    self.message_user(request, "%s a bien été supprimé." % obj.title)
                    obj.delete()
            return None
        deletable_objects = []
        for obj in queryset:
            deletable_objects.append(Rating.objects.filter(work=obj)[:10])
        context = {
            'queryset': queryset,
            'opts': self.model._meta,
            'deletable_objects': deletable_objects,
            'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME
        }
        return TemplateResponse(request, 'admin/merge_selected_confirmation.html', context)
    merge.short_description = "Fusionner les œuvres sélectionnées"


class GenreAdmin(admin.ModelAdmin):
    pass


class TrackAdmin(admin.ModelAdmin):
    pass

class ArtistAdmin(admin.ModelAdmin):
    search_fields = ('id', 'name')


class StudioAdmin(admin.ModelAdmin):
    pass


class EditorAdmin(admin.ModelAdmin):
    pass


class RatingAdmin(admin.ModelAdmin):
    pass


class PageAdmin(admin.ModelAdmin):
    pass


class SuggestionAdmin(admin.ModelAdmin):
    list_display = ('work', 'problem', 'date', 'user', 'is_checked')
    list_filter = ('problem',)
    actions = ['check_suggestions', 'uncheck_suggestions']

    def view_on_site(self, obj):
        return obj.work.get_absolute_url()

    def check_suggestions(self, request, queryset):
        rows_updated = queryset.update(is_checked=True)
        users_list = []
        for suggestion in queryset:
            if suggestion.problem == 'ref':  # Reference suggestion
                reference, created = Reference.objects.get_or_create(work=suggestion.work, url=suggestion.message)
                reference.suggestions.add(suggestion)
            if suggestion.user not in users_list:
                users_list.append(suggestion.user)
                suggestion.update_scores()
        if rows_updated == 1:
            message_bit = "1 suggestion"
        else:
            message_bit = "%s suggestions" % rows_updated
        self.message_user(request, "La validation de %s a réussi." % message_bit)
    check_suggestions.short_description = "Valider les suggestions sélectionnées"

    def uncheck_suggestions(self, request, queryset):
        rows_updated = queryset.update(is_checked=False)
        users_list = []
        for suggestion in queryset:
            if suggestion.user not in users_list:
                users_list.append(suggestion.user)
                suggestion.update_scores()
        if rows_updated == 1:
            message_bit = "1 suggestion"
        else:
            message_bit = "%s suggestions" % rows_updated
        self.message_user(request, "L'invalidation de %s a réussi." % message_bit)
    uncheck_suggestions.short_description = "Invalider les suggestions sélectionnées"


class SearchIssueAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'user')


class AnnouncementAdmin(admin.ModelAdmin):
    exclude = ('title',)


class RecommendationAdmin(admin.ModelAdmin):
    pass


class PairingAdmin(admin.ModelAdmin):
    list_display = ('artist', 'work', 'date', 'user', 'is_checked')
    actions = ['make_director', 'make_composer', 'make_author']

    def make_director(self, request, queryset):
        rows_updated = 0
        director = Role.objects.get(slug='director')
        for pairing in queryset:
            _, created = Staff.objects.get_or_create(work_id=pairing.work_id, artist_id=pairing.artist_id, role=director)
            if created:
                pairing.is_checked = True
                pairing.save()
                rows_updated += 1
        if rows_updated == 1:
            message_bit = "1 réalisateur a"
        else:
            message_bit = "%s réalisateurs ont" % rows_updated
        self.message_user(request, "%s été mis à jour." % message_bit)
    make_director.short_description = "Valider les appariements sélectionnés pour réalisation"

    def make_composer(self, request, queryset):
        rows_updated = 0
        composer = Role.objects.get(slug='composer')
        for pairing in queryset:
            _, created = Staff.objects.get_or_create(work_id=pairing.work_id, artist_id=pairing.artist_id, role=composer)
            if created:
                pairing.is_checked = True
                pairing.save()
                rows_updated += 1
        if rows_updated == 1:
            message_bit = "1 compositeur a"
        else:
            message_bit = "%s compositeurs ont" % rows_updated
        self.message_user(request, "%s été mis à jour." % message_bit)
    make_composer.short_description = "Valider les appariements sélectionnés pour composition"

    def make_author(self, request, queryset):
        rows_updated = 0
        author = Role.objects.get(slug='author')
        for pairing in queryset:
            _, created = Staff.objects.get_or_create(work_id=pairing.work_id, artist_id=pairing.artist_id, role=author)
            if created:
                pairing.is_checked = True
                pairing.save()
                rows_updated += 1
        if rows_updated == 1:
            message_bit = "1 auteur a"
        else:
            message_bit = "%s auteurs ont" % rows_updated
        self.message_user(request, "%s été mis à jour." % message_bit)
    make_author.short_description = "Valider les appariements sélectionnés pour écriture"


class ReferenceAdmin(admin.ModelAdmin):
    list_display = ['work', 'url']

class RankingInline(admin.TabularInline):
    model = Ranking
    fields = ('content_type', 'object_id', 'name', 'score', 'nb_ratings', 'nb_stars',)
    readonly_fields = ('name',)

    def name(self, instance):
        return str(instance.content_object)

class TopAdmin(admin.ModelAdmin):
    inlines = [
        RankingInline,
    ]
    readonly_fields = ('category', 'date',)

    def has_add_permission(self, request):
        return False

class RoleAdmin(admin.ModelAdmin):
    model = Role
    prepopulated_fields = {'slug': ('name',)}

admin.site.register(Work, WorkAdmin)
admin.site.register(Genre, GenreAdmin)
admin.site.register(Track, TrackAdmin)
admin.site.register(Artist, ArtistAdmin)
admin.site.register(Studio, StudioAdmin)
admin.site.register(Editor, EditorAdmin)
admin.site.register(Rating, RatingAdmin)
admin.site.register(Page, PageAdmin)
admin.site.register(Suggestion, SuggestionAdmin)
admin.site.register(SearchIssue, SearchIssueAdmin)
admin.site.register(Announcement, AnnouncementAdmin)
admin.site.register(Recommendation, RecommendationAdmin)
admin.site.register(Pairing, PairingAdmin)
admin.site.register(Reference, ReferenceAdmin)
admin.site.register(Top, TopAdmin)
admin.site.register(Role, RoleAdmin)
admin.site.register(Tag, TagAdmin)
admin.site.register(TaggedWork, TaggedWorkAdmin)