#!/usr/bin/env python3
"""
IEEE Reference Formatter

This script helps format academic references according to IEEE citation style.
It provides templates and validation for common reference types.
"""

def format_journal_article(authors, title, journal, volume, number, pages, month, year, doi=None):
    """
    Format a journal article reference in IEEE style.
    
    Args:
        authors: List of author names in "F. Lastname" format
        title: Article title
        journal: Journal name (abbreviated per IEEE standards)
        volume: Volume number
        number: Issue number
        pages: Page range as "XX-XX"
        month: Month abbreviation (Jan., Feb., etc.)
        year: Publication year
        doi: Optional DOI
    
    Returns:
        Formatted IEEE reference string
    """
    # Format author list
    if len(authors) <= 6:
        author_str = ', '.join(authors[:-1]) + (' and ' if len(authors) > 1 else '') + authors[-1]
    else:
        author_str = authors[0] + ' et al.'
    
    # Build reference
    ref = f'{author_str}, "{title}," {journal}, vol. {volume}, no. {number}, pp. {pages}, {month} {year}'
    
    if doi:
        ref += f', doi: {doi}'
    
    return ref + '.'


def format_conference_paper(authors, title, conference, city, country, year, pages, doi=None):
    """
    Format a conference paper reference in IEEE style.
    
    Args:
        authors: List of author names in "F. Lastname" format
        title: Paper title
        conference: Conference name (abbreviated)
        city: Conference city
        country: Conference country
        year: Publication year
        pages: Page range as "XX-XX"
        doi: Optional DOI
    
    Returns:
        Formatted IEEE reference string
    """
    # Format author list
    if len(authors) <= 6:
        author_str = ', '.join(authors[:-1]) + (' and ' if len(authors) > 1 else '') + authors[-1]
    else:
        author_str = authors[0] + ' et al.'
    
    # Build reference
    ref = f'{author_str}, "{title}," in Proc. {conference}, {city}, {country}, {year}, pp. {pages}'
    
    if doi:
        ref += f', doi: {doi}'
    
    return ref + '.'


def format_book(authors, title, edition, city, state, publisher, year):
    """
    Format a book reference in IEEE style.
    
    Args:
        authors: List of author names in "F. Lastname" format
        title: Book title
        edition: Edition (e.g., "2nd ed." or None for first edition)
        city: Publisher city
        state: Publisher state/country abbreviation
        publisher: Publisher name
        year: Publication year
    
    Returns:
        Formatted IEEE reference string
    """
    # Format author list
    if len(authors) <= 6:
        author_str = ', '.join(authors[:-1]) + (' and ' if len(authors) > 1 else '') + authors[-1]
    else:
        author_str = authors[0] + ' et al.'
    
    # Build reference
    edition_str = f', {edition}' if edition else ''
    ref = f'{author_str}, {title}{edition_str}. {city}, {state}: {publisher}, {year}'
    
    return ref + '.'


def format_website(authors, title, website, url, access_date):
    """
    Format a website reference in IEEE style.
    
    Args:
        authors: List of author names in "F. Lastname" format or None
        title: Page/article title
        website: Website name
        url: Full URL
        access_date: Access date as "Month Day, Year"
    
    Returns:
        Formatted IEEE reference string
    """
    if authors:
        if len(authors) <= 6:
            author_str = ', '.join(authors[:-1]) + (' and ' if len(authors) > 1 else '') + authors[-1]
        else:
            author_str = authors[0] + ' et al.'
        author_str += '. '
    else:
        author_str = ''
    
    ref = f'{author_str}"{title}." {website}. {url} (accessed {access_date})'
    
    return ref + '.'


def validate_author_format(author):
    """
    Check if author name follows IEEE format (F. Lastname or F. M. Lastname).
    
    Args:
        author: Author name string
    
    Returns:
        Boolean indicating if format is valid
    """
    parts = author.split()
    
    # Should have at least 2 parts (initial and lastname)
    if len(parts) < 2:
        return False
    
    # Check that all but last part are initials (single letter + period)
    for part in parts[:-1]:
        if len(part) != 2 or part[1] != '.':
            return False
    
    return True


def month_abbreviation(month):
    """
    Convert full month name to IEEE abbreviation.
    
    Args:
        month: Full month name
    
    Returns:
        IEEE-style abbreviated month
    """
    months = {
        'january': 'Jan.',
        'february': 'Feb.',
        'march': 'Mar.',
        'april': 'Apr.',
        'may': 'May',
        'june': 'Jun.',
        'july': 'Jul.',
        'august': 'Aug.',
        'september': 'Sep.',
        'october': 'Oct.',
        'november': 'Nov.',
        'december': 'Dec.'
    }
    return months.get(month.lower(), month)


# Example usage
if __name__ == "__main__":
    print("IEEE Reference Formatter Examples\n")
    
    # Journal article example
    print("Journal Article:")
    journal_ref = format_journal_article(
        authors=["J. Smith", "R. Johnson", "M. Williams"],
        title="Deep learning approaches for medical image analysis",
        journal="IEEE Trans. Med. Imaging",
        volume="42",
        number="3",
        pages="234-245",
        month="Mar.",
        year="2023",
        doi="10.1109/TMI.2023.1234567"
    )
    print(f"[1] {journal_ref}\n")
    
    # Conference paper example
    print("Conference Paper:")
    conf_ref = format_conference_paper(
        authors=["P. Kumar", "S. Patel"],
        title="Machine learning for network optimization",
        conference="IEEE Int. Conf. Commun. (ICC)",
        city="Rome",
        country="Italy",
        year="2023",
        pages="456-461"
    )
    print(f"[2] {conf_ref}\n")
    
    # Book example
    print("Book:")
    book_ref = format_book(
        authors=["D. Patterson", "J. Hennessy"],
        title="Computer Architecture: A Quantitative Approach",
        edition="6th ed.",
        city="Cambridge",
        state="MA, USA",
        publisher="Morgan Kaufmann",
        year="2017"
    )
    print(f"[3] {book_ref}\n")
    
    # Website example
    print("Website:")
    web_ref = format_website(
        authors=["T. Brown"],
        title="Language models are few-shot learners",
        website="OpenAI Blog",
        url="https://openai.com/blog/gpt-3",
        access_date="Jan. 15, 2023"
    )
    print(f"[4] {web_ref}\n")
