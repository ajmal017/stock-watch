import datetime
from decimal import Decimal

import pytest
import responses
from django.urls import reverse

from StockWatch.factories import CompanyFactory, StockDataFactory
from StockWatch.main.models import Company, Currency, Firm, StockData, User


def assert_redirects(r, url):
    assert hasattr(r, 'redirect_chain'), 'Response was not a redirect. Did you use follow=True?'
    response_url, _ = r.redirect_chain[0]
    assert response_url == url, 'Response redirected to wrong page: ' + response_url


def assert_contains(r, s, status_code=200, count=None):
    assert r.status_code == status_code
    content = r.content.decode()
    if count:
        assert content.count(s) == count, content
    else:
        assert s in content, content


def assert_not_contains(r, s, status_code=200):
    assert r.status_code == status_code
    content = r.content.decode()
    assert s not in content, content


@pytest.mark.django_db
def test_redirect_not_authed(client):
    User.objects.create_user(
        first_name='Tom',
        last_name='Owner',
        email='testing@stockwatch.com',
        password='testing',
        firm=Firm.objects.create(name='123 Firm Ltd'),
    )
    r = client.get('/', follow=True)
    assert_redirects(r, '/login/')


@pytest.mark.django_db
def test_login(client):
    User.objects.create_user(
        first_name='Tom',
        last_name='Owner',
        email='testing@stockwatch.com',
        password='testing',
        firm=Firm.objects.create(name='123 Firm Ltd'),
    )
    r = client.post('/login/', data={'username': 'testing@stockwatch.com', 'password': 'testing'}, follow=True)
    assert_redirects(r, '/')


@pytest.mark.django_db
def test_logout(auth_client):
    r = auth_client.post(reverse('logout'), follow=True)
    assert_redirects(r, '/login/')
    r = auth_client.get('/', follow=True)
    assert_redirects(r, '/login/')


@pytest.mark.django_db
@responses.activate
def test_timeseries_options(auth_client, timeseries_example, gb_currency):
    company = CompanyFactory(symbol='FOO', name='FooBar holdings', currency=gb_currency)
    responses.add(
        'GET', 'https://eodhistoricaldata.com/api/eod/FOO.LSE/', body=timeseries_example, content_type='text/csv'
    )
    url = reverse('search')
    r = auth_client.get(url)
    assert r.status_code == 200
    r = auth_client.post(
        url,
        data={
            'date': datetime.date(2019, 1, 4).strftime('%d/%m/%Y'),
            'company': company.id,
            'quantity': 2,
            'reference': 'Client 1',
        },
    )
    assert r.status_code == 302
    sd = StockData.objects.get()
    assert sd.high == Decimal('800')
    assert sd.quarter == Decimal('575')
    assert sd.date == datetime.date(2019, 1, 4)
    assert sd.company == Company.objects.get(name='FooBar holdings')
    r = auth_client.get(url)
    assert sd.company.name in r.content.decode()
    assert 'value="Client 1"' in r.content.decode()


@pytest.mark.django_db
@responses.activate
def test_timeseries_weekend(auth_client, timeseries_example, gb_currency):
    company = CompanyFactory(symbol='FOO', name='FooBar holdings', currency=gb_currency)
    responses.add(
        'GET', 'https://eodhistoricaldata.com/api/eod/FOO.LSE/', body=timeseries_example, content_type='text/csv'
    )
    r = auth_client.post(
        reverse('search'),
        data={
            'date': datetime.date(2019, 1, 5).strftime('%d/%m/%Y'),
            'company': company.id,
            'quantity': 2,
            'reference': 'Client 1',
        },
    )
    assert r.status_code == 302
    sd = StockData.objects.get()
    assert sd.high == Decimal('800')
    assert sd.quarter == Decimal('575')
    assert sd.date == datetime.date(2019, 1, 4)
    assert sd.company == Company.objects.get(name='FooBar holdings')
    r = auth_client.get(reverse('search'))
    assert sd.company.name in r.content.decode()
    assert 'value="Client 1"' in r.content.decode()


@pytest.mark.django_db
@responses.activate
def test_timeseries_no_data(auth_client, gb_currency):
    company = CompanyFactory(symbol='FOO', name='FooBar holdings', currency=gb_currency)
    responses.add('GET', 'https://eodhistoricaldata.com/api/eod/FOO.LSE/', body='', content_type='text/csv')
    r = auth_client.post(
        reverse('search'),
        data={
            'date': datetime.date(2019, 1, 5).strftime('%d/%m/%Y'),
            'company': company.id,
            'quantity': 2,
            'reference': 'Client 1',
        },
    )
    assert r.status_code == 200
    assert 'No stock data for that day' in r.content.decode()
    assert not StockData.objects.exists()


@pytest.mark.django_db
@responses.activate
def test_decimal_error(auth_client, timeseries_example_bad, gb_currency):
    company = CompanyFactory(symbol='FOO', name='FooBar holdings', currency=gb_currency)
    responses.add(
        'GET', 'https://eodhistoricaldata.com/api/eod/FOO.LSE/', body=timeseries_example_bad, content_type='text/csv'
    )
    url = reverse('search')
    r = auth_client.get(url)
    assert r.status_code == 200
    r = auth_client.post(
        url,
        data={
            'date': datetime.date(2019, 1, 1).strftime('%d/%m/%Y'),
            'company': company.id,
            'quantity': 2,
            'reference': 'Client 1',
        },
    )
    assert 'Something went wrong' in r.content.decode()


@pytest.mark.django_db
@responses.activate
def test_eod_bad_response(auth_client):
    responses.add('GET', 'https://eodhistoricaldata.com/api/search/Auto/', json={}, status=500)
    r = auth_client.get(reverse('symbol-search'), {'q': 'Auto'})
    assert r.json() == []


@pytest.mark.django_db
def test_archive(auth_client, gb_currency):
    StockDataFactory(currency=gb_currency, user=auth_client.user, reference='123ref')
    StockDataFactory(currency=gb_currency, reference='456ref')

    r = auth_client.get(reverse('archive'))
    assert_contains(r, '123ref')
    assert_not_contains(r, '456ref')


@pytest.mark.django_db
def test_archive_filter(auth_client, gb_currency):
    StockDataFactory(currency=gb_currency, user=auth_client.user, reference='123ref', company__name='company1')
    StockDataFactory(currency=gb_currency, user=auth_client.user, reference='456ref', company__name='company2')

    r = auth_client.get(reverse('archive'))
    assert_contains(r, '123ref')
    assert_contains(r, '456ref', count=3)  # Twice in select dropdown

    r = auth_client.get(reverse('archive') + '?ref=123ref')
    assert_contains(r, '123ref')
    assert_contains(r, '456ref', count=2)


@pytest.mark.django_db
def test_zero_decimal(auth_client, gb_currency):
    another_currency = Currency.objects.create(code='XXX', symbol='£', name='GBP')
    StockDataFactory(currency=gb_currency, user=auth_client.user, reference='123ref', company__name='company1')
    StockDataFactory(currency=another_currency, user=auth_client.user, reference='456ref', company__name='company2')
    r = auth_client.get('/')
    assert_contains(r, '£250.00')
    assert_contains(r, '250.00p')


@pytest.mark.django_db
def test_archive_export(auth_client, gb_currency):
    StockDataFactory(currency=gb_currency, user=auth_client.user, reference='123ref', company__name='company1')
    StockDataFactory(currency=gb_currency, user=auth_client.user, reference='456ref', company__name='company2')

    r = auth_client.post(reverse('archive-export'))
    assert r.content.decode() == (
        'Reference,Company,Date,High,Low,Quarter,Amount,Gross Value,currency\r\n'
        '456ref,company2,2014-01-01,400.000000,200.000000,250.000000,1,250.000000,GBX\r\n'
        '123ref,company1,2014-01-01,400.000000,200.000000,250.000000,1,250.000000,GBX\r\n'
    )

    r = auth_client.post(reverse('archive-export') + '?ref=123ref')
    assert r.content.decode() == (
        'Reference,Company,Date,High,Low,Quarter,Amount,Gross Value,currency\r\n'
        '123ref,company1,2014-01-01,400.000000,200.000000,250.000000,1,250.000000,GBX\r\n'
    )
