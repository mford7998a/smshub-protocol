# SMSHUB Agent

# Protocol

### Version of March 6, 2024


## Contents

### Contents Error! Bookmark not defined.

### Description Error! Bookmark not defined.

### General actions on the example of the vk service (VKontakte) 4

### 1. Quantity request (GET_SERVICES) 5

### 2. Number request (GET_NUMBER) 7

### 3. Finishing activation (FINISH_ACTIVATION) 9

### 4. SMS delivery to the SMSHUB server (PUSH_SMS) 10

### Protocol testing Error! Bookmark not defined.

### Appendix 1. List of countries 13

### Appendix 2. List of operators 14

### Appendix 3. List of abbreviated services’ names 15

### Appendix 4. Activation status 16

### Appendix 5. Request status 17

### Appendix 6. Currency 18


## Description

```
Requests 1-3 are sent by the smshub server to the agent server. You can use both the http
```
and https protocols. Each request has a key parameter. The key can be obtained in your personal

account.

```
URL - https://SMSHUB,
there SMSHUB may be agent.ru:port/smshub or agent.ru/smshub.php
```
```
The requirements are as follows:
```
- the request/response format must be JSON
- use UTF-8 encoding.
- use the user-agent header in each request to the smshub server.
- use the gzip compression method in each request/response.

### Field types:

### int number is an integer value in the range from -2,147,483,648 to 2,147,483,

### Uint number is an unsigned integer value in the range from 0 to 2,147,483,

### long number is an integer value in the range from -9 223 372 036 854 775 808 to 9

### 223 372 036 854 775 807

### Ulong number is an unsigned integer value in the range from 0 to 9 223 372 036 854

### 775 807

### cur number is a real value containing 2 decimal signs for rubles or 4 decimal signs

### for dollars, e.g. 134.

### boolean is a literal accepting the true or false values

### string is a string value of unlimited length


## General actions on the example of the vk service

## (VKontakte)

1. One every 10-20 seconds the smshub server will send a GET_SERVICES request (request
    1).
2. Furthermore, if your server returns a non-zero VK quantity we will send a GET_NUMBER
    request to your server based on the order of priority (request 2).
3. For example, you give us the number 79281234567 for VK. From this moment onwards you
    are required to start sending all incoming messages meant for 79281234567 to the smshub
    server (request 4).
    The logic behind deciding whether a message is for VK or another service must be in one
    place. We have the constantly updating FILTER for SMS. It is easier to keep that filter up-to-
    date in one place.
4. After using the phone number we will send you the finish activation status. A status equal to

```
3 means that a user has successfully received an SMS and that the reward has been added
to your agent balance.
Please read Appendix 4 for information about other statuses.
```

## 1. Quantity request (GET_SERVICES)

```
The request provides information about how many numbers are available for selling.
A POST request is performed by the smshub server to the agent server.
```
```
Request fields:
```
```
Response fields:
Field Type Necessity Описание
```
```
status string Required The response status.
Appendix 5
countryList array Required List of countries
```
```
countryList:
Поле Тип Обязательность Описание
```
```
country string Required Appendix 1
```
```
operatorMap Associative array Required Key - Operator
Appendix 2
value is an
associative array of
services*
```
```
*An Associative array of services: key is the short name of the service (see appendix 3),
value is the quantity of numbers available for the service (type-int).
```
**WARNING.** It is required and expected that you return the current quantity of

simultaneously available sim cards. For example, if you have a sim bank with 512 ports, but there

are only 60 gsm modules, you must send back a quantity of 60, but not 512. If you violate this

condition, the system will automatically block number reception from your server for 30 minutes.

```
Field Type Necessity Description/Value
```
```
action string Required GET_SERVICES
```
```
key string Required Protocol key
```

Request example:
{
"action": "GET_SERVICES",
"key": "123"
}

Response example:
{
"countryList": [
{
"country": "russia",
"operatorMap": {
"beeline": {
"vk": 10,
"ok": 15,
"wa": 20
},
"megafon": {
"vk": 0,
"ok": 10,
"wa": 32
} }
},
{
"country": "ukraine",
"operatorMap": {
"life": {
"vk": 0,
"ok": 10,
"wa": 32
}
}
}
],
"status": "SUCCESS"
}


## 2. Number request (GET_NUMBER)

A POST request is performed by the smshub server to the agent
server.
Request fields:

```
Field Type Necessity Description/Value
```
```
action string Required GET_NUMBER
```
```
key string Required protocol key
```
```
country string Required Appendix 1
```
```
service string Required Appendix 3
```
```
operator string Required Appendix 2
```
```
sum cur Required The amount that you will
receive for a successfully
sold service
```
```
currency uint Required Appendix 6
```
```
exceptionPhoneSet array Optional The list of prefixes that
you must NOT provide
when a number is
requested
```
Response fields:

```
Field Type Necessity Description
```
```
status string Required Response status.
Appendix 5
```
```
number Ulong Required Phone number with the
country code
```
```
activationId Ulong Required Activation Id in the
agent's system
```
* If we include any data in exceptionPhoneSet, for instance 7918 and 7928, that means that you
exclude all phone numbers with these prefixes from your pool of available numbers (in this case
7918 and 7928). The length of the prefixes can be different and can be more than the default
prefix length of the country code (for example: 792831).

Request example:
{
"country": "russia",
"operator": "mts",
"service": "vk",
"sum": 20.00,
"action": "GET_NUMBER",
"currency": 643,
"key": "1234"
}


Request example with exceptionPhoneSet:
{
"country": "russia",
"operator": "any",
"service": "vk",
"sum": 10,
“currency”: 643,
"exceptionPhoneSet": [
"7918",
"79281"
],
"action": "GET_NUMBER",
"key": "1234"
}

Response example:
{
"number": 79281234567,
"activationId": 355,
"status": "SUCCESS"
}

Response example in case if numbers are unavailable:
{
"status": "NO_NUMBERS"
}


## 3. Finishing activation (FINISH_ACTIVATION)

A POST request is performed by the smshub server to the agent

Request fields:

Response fields:

```
Field Type Necessity Description
```
```
status string Required Response status.
Appendix 5
```
```
* The control of the activation process is done only by the smshub server.
```
Sometimes, for some possible reason (e.g. network issues), we may not receive a

response from your server. Therefore, when the smshub server sends the finish activation

request again you must check the activation by id on your side and, if you have this

activation, send SUCCESS response status (idempotence law).

Request example:
{
"activationId": 100,
"status": 3,
"action": "FINISH_ACTIVATION",
"key": "123"
}

Response example:
{
"status": "SUCCESS"
}

```
Field Type Necessity Description/Value
```
```
action string Required FINISH_ACTIVATION
```
```
key string Required protocol key
```
```
activationId Ulong Required Activation Id received in
the second request
```
```
status Uint Required Activation status.
Appendix 4
```

## 4. SMS delivery to the smshub server (PUSH_SMS)

A POST request is performed by the agent server to the smshub server.

### https://agent.unerio.com/agent/api/sms

Request fields:

```
Field Type Necessity Description/Value
```
```
action string Required PUSH_SMS
```
```
key string Required Protocol key
```
```
smsId Ulong Required SMS Id in the agent's
system
```
phone Ulong Required (^) The phone number that
receives the SMS, **with
the country code**
phoneFrom string Required The phone number from
which the SMS was sent
(it can be a letter
naming)
text string Required SMS text
Response fields:
**Field Type Necessity Description**
status string Required Response status.
Appendix 5
Request example:
{
"smsId": 1,
"phoneFrom": "Vk",
"phone": 79281234567,
"text": "VK: 33708 – your code for VKontakte registration», "action":
«PUSH_SMS",
"key": "12345"
}
Response example:
{
"status": "SUCCESS"
}
If you receive a response with the SUCCESS status then mark the SMS as successfully
delivered in your database and do not send it again. If the returned status is different from
SUCCESS then keep sending the SMS again with 10-seconds delays until you receive a response
with the SUCCESS status.


## Protocol testing

### MUST-READ

```
After implementing the protocol the smshub developers will test it. Write your url address to
the smshub support when you are ready. From that moment onwards your server must be
available 24/7. We will start the test as soon as possible.
```
You must pre-test implementation of protocol. Firstly send your url to our support. After that open

### the link https://agent.unerio.com/docs.html. You can test methods of getting numbers, getting

quantity, finishing activation, and also you can check the efficiency of sms delivery to our server.

```
List of tests to be conducted:
```
**1. Correct processing of finishing activation request.**

```
Activation is managed ONLY by smshub. For reasons beyond our control (network
problems), we may not receive a response from you about a successful status change.
Therefore, if smshub sends the finishing activation status again, you should check if the
activation exists according to your id, and if it does, then send status SUCCESS. Also, you
should NOT complete the activation by yourself. Only the finishing request from smshub
should complete the activation on your side.
```
**2. SMS test.**

```
Once a text message has entered your database, you should forward it to us as soon as
possible. If you receive a text message, send it to us immediately.
If you receive a response with the status SUCCESS, then mark the text message as
successfully delivered in your database and do not send it again. If you get a status different
from SUCCESS, then repeat the request with a delay of 10 seconds until you get the status
SUCCESS.
If you send one and the same SMS after we reply with SUCCESS status - test failed.
```
**3. Types of fields.**

```
Carefully check the types of fields you send through the protocol. If the protocol description
says that the field is of numeric type, and you send smsId : «123» - test failed.
```
**4. A phone number should contain the country code.**

```
The number field in the phone number request and the phone field in the sms delivery request
must be NUMERIC and with the country CODE.
```
**5. Time of providing a number from you should be minimal**
If the time of providing a number exceeds 3 seconds – **test failed.**


**6. The quantity of numbers returned by request 1 should reflect the real**

```
situation.
If you return 100 vk numbers and there are actually 30 of them, then 70 requests will return
with a NO_NUMBERS response – test failed.
```
**7. Testing excluding prefixes.**

```
You must process the exceptionPhoneSet field correctly when requesting GET_NUMBER. If
you provide a phone number which prefix is on the list – test failed.
```

## Appendix 1. List of countries

Full list of countries https://smshub.org/countries

```
If you provide country that is not present in the list, please contact our technical support.
```

## Appendix 2. List of operators

Full list of operators https://smshub.org/countries

```
If you provide an operator that is not present in the list, please contact our technical
support.
```
```
**"Any" operator should only be returned if you do not have a an opportunity to divide
```
operators by some specific country.

```
If you provide a country with operators division, you cannot return any for that country.
If you have started to provide a country with operators division, it will not be possible to
```
change response for this country to "any" without contacting tech support.

```
If you have started to provide a country without operator division, i.e. you send any, it will
```
not be possible to switch to operator division for this country without contacting technical support.


## Appendix 3. List of abbreviated services’ names

Full list of services https://smshub.org/countries


## Appendix 4. Activation status

Used when activation finishing is requested.

```
Status Value
```
```
1 No longer provide numbers for that service
```
```
3 Successfully sold
```
```
4 Cancelled
```
```
5 Returned
```
```
Status 1 - Number cancelation. No need to provide a number anymore. Possible
```
reason for cancelation is that the number has already been sold for this service earlier.

```
Status 3 - The number has been successfully sold for the service. User has successfully
```
received sms and you have received a reward in your smshub account.

```
Status 4 - Number canceled. You can give this number to us 3 more times (that is only 4
```
times in total if it was canceled with status 4).

```
Possible reason for cancelation is that the number is not suitable for the user or was
```
already registered in the service earlier.

```
Status 5 - Refund to a user for the number. There are cases when the user is refunded for
```
activation. In this case we will notify you about it with status 5.


## Appendix 5. Request status

_Status_ field value in the requests' responses:

```
status Description
```
```
SUCCESS Request successfully completed
```
```
ERROR Error occured during the request perfomance. You
need to fill the error field with the error description.
```
```
NO_NUMBERS No numbers available.
You can only return the status to a number receiving
request.
```
### General format of a successful response to a request:

### {

### "status": "SUCCESS",

### //data

### }

### General format of a response when an error occurs:

### {

### "status": "ERROR",

### "error": "error description"

### }


## Appendix 6. Currency

Indicates the currency with which the number is purchased. It is transmitted in the ISO- 4217
numeric format.

List of supported currencies and values:

```
Currency name Parameter value
```
```
Russian ruble 643
```
```
US Dollar 840
```

