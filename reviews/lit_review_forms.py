from django import forms

from reviews.models import LitReview


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class LitReviewStage1Form(forms.ModelForm):
    research_context = forms.CharField(
        label='Main Research Context',
        help_text='Describe the domain/context of the study (scope, setting, population, and focus).',
        widget=forms.Textarea(attrs={'rows': 4}),
    )
    research_questions = forms.CharField(
        label='Research Question(s)',
        help_text='Enter one question per line.',
        widget=forms.Textarea(attrs={'rows': 7}),
    )

    class Meta:
        model = LitReview
        fields = ['research_context', 'target_word_count']

    def clean_target_word_count(self):
        value = self.cleaned_data['target_word_count']
        if value < 800:
            raise forms.ValidationError('Target word count should be at least 800.')
        if value > 20000:
            raise forms.ValidationError('Target word count should be 20,000 or less.')
        return value

    def clean_research_questions(self):
        raw = self.cleaned_data.get('research_questions') or ''
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        unique = []
        seen = set()
        for item in lines:
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)

        if not unique:
            raise forms.ValidationError('Enter at least one research question.')
        if len(unique) > 12:
            raise forms.ValidationError('Please limit to 12 research questions.')
        return unique

    def clean_research_context(self):
        value = (self.cleaned_data.get('research_context') or '').strip()
        if not value:
            raise forms.ValidationError('Enter the main research context.')
        if len(value) < 20:
            raise forms.ValidationError('Research context is too short. Add more detail.')
        return value


class LitRISUploadForm(forms.Form):
    ris_file = forms.FileField(help_text='Upload a RIS file.')


class LitExcelUploadForm(forms.Form):
    excel_file = forms.FileField(help_text='Upload an Excel file with columns: title, pdf_link.')


class LitNumberedPDFUploadForm(forms.Form):
    pdf_files = forms.FileField(
        widget=MultipleFileInput(attrs={'multiple': True}),
        help_text='Upload files named 1.pdf, 2.pdf, ... mapped to Excel row order.',
    )
