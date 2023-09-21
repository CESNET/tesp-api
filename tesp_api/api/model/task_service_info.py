from typing import List
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


class TesServiceType(BaseModel):
    group: str = Field(..., example='org.ga4gh', description='Namespace in reverse domain name format. Use org.ga4gh'
                                                             'for implementations compliant with official GA4GH '
                                                             'specifications. For services with custom APIs not '
                                                             'standardized by GA4GH, or implementations diverging '
                                                             'from official GA4GH specifications, use a different '
                                                             'namespace (e.g. your organization’s reverse domain '
                                                             'name).')
    artifact: str = Field(..., example='tes')
    version: str = Field(..., example="1.0.0", description='Version of the API or specification. GA4GH specifications'
                                                           ' use semantic versioning.')


class TesServiceOrganization(BaseModel):
    name: str = Field(..., example='My organization',
                      description='Name of the organization responsible for the service')
    url: HttpUrl = Field(..., example='https://example.com',
                         description='URL of the website of the organization (RFC 3986 format)')


class TesServiceInfo(BaseModel):
    id: str = Field(..., example='org.ga4gh.myservice', description='Unique ID of this service. Reverse domain name'
                                                                    'notation is recommended, though not required. '
                                                                    'The identifier should attempt to be globally '
                                                                    'unique so it can be used in downstream '
                                                                    'aggregator services e.g. Service Registry.')

    name: str = Field(..., example='example: My project', description='Name of this service. Should be human readable.')
    type: TesServiceType = Field(...)

    description: str = Field(None, example='This service provides...', description='Description of the service. Should'
                                                                                   'be human readable and provide '
                                                                                   'information about the service.')

    organization: TesServiceOrganization = Field(..., description='Organization providing the service')
    contactUrl: HttpUrl = Field(None, example='mailto:support@example.com',
                                description='URL of the contact for the provider of this'
                                            'service, e.g. a link to a contact form (RFC 3986 format), or an email ('
                                            'RFC 2368 format).')

    documentationUrl: HttpUrl = Field(None, example='https://docs.myservice.example.com',
                                      description='URL of the documentation of this'
                                                  'service (RFC 3986 format). This should help someone learn how to '
                                                  'use your service, including any specifics required to '
                                                  ' access data, e.g. authentication.')

    createdAt: datetime = Field(None, example='2019-06-04T12:58:19Z',
                                description='Timestamp describing when the service was first'
                                            ' deployed and available (RFC 3339 format)')
    updatedAt: datetime = Field(None, example='2019-06-04T12:58:19Z',
                                description='Timestamp describing when the service was last'
                                            ' updated (RFC 3339 format)')

    environment: str = Field(None, example='test',
                             description='Environment the service is running in. Use this to distinguish'
                                         'between production, development and testing/staging deployments. Suggested '
                                         'values are prod, test, dev, staging. However this is advised and not '
                                         'enforced.')
    version: str = Field(..., example='1.0.0',
                         description='Version of the service being described. Semantic versioning is'
                                     'recommended, but other identifiers, such as dates or commit hashes, are also '
                                     'allowed. The version should be changed whenever the service is updated.')

    storage: List[HttpUrl] = Field(None,
                                   example=['file:///path/to/local/funnel-storage', 's3://ohsu-compbio-funnel/storage'],
                                   description='Lists some, but not necessarily all, storage locations supported by '
                                               'the service.')
