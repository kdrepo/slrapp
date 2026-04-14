from django import forms
from django.forms import inlineformset_factory

from .constants import DEFAULT_EXCLUSION_CRITERIA, DEFAULT_INCLUSION_CRITERIA
from .models import ResearchQuestion, Review


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = [
            'title',
            'objectives',
            'pico_population',
            'pico_intervention',
            'pico_comparison',
            'pico_outcomes',
            'inclusion_criteria',
            'exclusion_criteria',
        ]
        widgets = {
            'objectives': forms.Textarea(attrs={'rows': 4}),
            'pico_population': forms.Textarea(attrs={'rows': 3}),
            'pico_intervention': forms.Textarea(attrs={'rows': 3}),
            'pico_comparison': forms.Textarea(attrs={'rows': 3}),
            'pico_outcomes': forms.Textarea(attrs={'rows': 3}),
            'inclusion_criteria': forms.Textarea(attrs={'rows': 4}),
            'exclusion_criteria': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.is_bound and (not self.instance or not self.instance.pk):
            self.fields['inclusion_criteria'].initial = DEFAULT_INCLUSION_CRITERIA
            self.fields['exclusion_criteria'].initial = DEFAULT_EXCLUSION_CRITERIA


class ReviewFormalizationConfirmForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = [
            'pico_population',
            'pico_intervention',
            'pico_comparison',
            'pico_outcomes',
            'inclusion_criteria',
            'exclusion_criteria',
        ]
        widgets = {
            'pico_population': forms.Textarea(attrs={'rows': 3}),
            'pico_intervention': forms.Textarea(attrs={'rows': 3}),
            'pico_comparison': forms.Textarea(attrs={'rows': 3}),
            'pico_outcomes': forms.Textarea(attrs={'rows': 3}),
            'inclusion_criteria': forms.Textarea(attrs={'rows': 5}),
            'exclusion_criteria': forms.Textarea(attrs={'rows': 5}),
        }


class ResearchQuestionForm(forms.ModelForm):
    class Meta:
        model = ResearchQuestion
        fields = ['question_text', 'type']
        widgets = {
            'question_text': forms.Textarea(attrs={'rows': 2}),
        }


class RISUploadForm(forms.Form):
    ris_file = forms.FileField(help_text='Upload a .ris file exported from Scopus.')


class TitlesExcelUploadForm(forms.Form):
    titles_file = forms.FileField(help_text='Upload .csv or .xlsx with paper titles in the first column.')


class PDFManualUploadForm(forms.Form):
    paper_id = forms.IntegerField(widget=forms.HiddenInput())
    pdf_file = forms.FileField(help_text='Upload a PDF for this paper.')


ResearchQuestionFormSet = inlineformset_factory(
    Review,
    ResearchQuestion,
    form=ResearchQuestionForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
