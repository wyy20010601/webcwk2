import json

from django.db import transaction

from paymentservice.models import User, Order, RefundOrder
from rest_framework.decorators import api_view
from datetime import datetime
import random
from django import forms
from django.http.response import JsonResponse


class RegistrationForm(forms.Form):
    Name = forms.CharField(max_length=50)
    Email = forms.EmailField()
    Password = forms.CharField(max_length=50)


class OrderForm(forms.Form):
    MerchantOrderId = forms.CharField(max_length=50)
    Price = forms.FloatField()


class RefundForm(forms.Form):
    PaymentId = forms.IntegerField()
    Price = forms.FloatField()


@api_view(['POST'])
def Register(request):
    try:
        data = json.loads(request.body)
        form = RegistrationForm(data)
        if not form.is_valid():
            return JsonResponse(form.errors, status=400)
        name = form.cleaned_data['Name']
        email = form.cleaned_data['Email']
        password = form.cleaned_data['Password']
        user = User.objects.create(name=name, password=password, email=email, balance=0)
        if user:
            return JsonResponse({'AccountID': user.id, 'Name': name})
        else:
            return JsonResponse('Account creation failed', status=500)
    except Exception as e:
        return JsonResponse(str(e), status=500)


@api_view(['POST'])
def Login(request):
    try:
        data = json.loads(request.body)
        id = data.get('ID')
        password = data.get('Password')
        if not id or not password:
            return JsonResponse('ID and Password are required', status=400)
        user = User.objects.filter(id=id).first()
        if user and password == user.password:
            request.session['id'] = id
            return JsonResponse('success', status=200, safe=False)
        else:
            return JsonResponse('Incorrect ID or Password', status=400)
    except Exception as e:
        return JsonResponse(str(e), status=500)


@api_view(['POST'])
def Orders(request):
    try:
        if not request.session.get('id'):
            return JsonResponse('Not logged in', status=400)
        data = json.loads(request.body)
        form = OrderForm(data)
        if not form.is_valid():
            return JsonResponse(form.errors, status=400)
        merchant_order_id = form.cleaned_data['MerchantOrderId']
        price = form.cleaned_data['Price']
        to_account = request.session['id']
        stamp = str(int(datetime.now().timestamp())) + str(random.randint(1000, 9999))
        order = Order.objects.create(merchant_order_id=merchant_order_id, order_time=datetime.now(),
                                     price=price, stamp=stamp, to_account=to_account)
        if order:
            return JsonResponse({'PaymentId': order.id, 'Stamp': order.stamp})
        else:
            return JsonResponse('Order creation failed', status=500)
    except Exception as e:
        return JsonResponse(str(e), status=500)


@api_view(['POST'])
def Pay(request):
    try:
        if not request.session.get('id'):
            return JsonResponse('Not logged in', status=400)
        data = json.loads(request.body)
        payment_id = data.get('PaymentId')
        from_account = User.objects.get(id=request.session['id'])
        order = Order.objects.get(id=payment_id)

        # 检查订单是否存在
        if not order:
            return JsonResponse({'error': 'Invalid PaymentId'}, status=400)

        # 检查用户余额是否充足
        if from_account.balance < order.price:
            return JsonResponse({'error': 'Insufficient balance'}, status=400)

        # 更新订单信息和用户余额
        from_account.balance -= order.price
        order.from_account = from_account.id
        order.payment_time = datetime.now()
        to_account_id = order.to_account
        to_account = User.objects.get(id=to_account_id)
        to_account.balance += order.price
        order.save()
        from_account.save()
        to_account.save()

        # 返回成功信息
        return JsonResponse({'Stamp': order.stamp}, status=200)

    except User.DoesNotExist:
        return JsonResponse({'error': 'User does not exist'}, status=400)

    except Order.DoesNotExist:
        return JsonResponse({'error': 'Invalid PaymentId'}, status=400)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@api_view(['POST'])
def Refund(request):
    try:
        if not request.session:
            return JsonResponse({'error': 'No login'}, status=400)

        data = json.loads(request.body)
        payment_id = data.get('PaymentId')
        price = int(data.get('Price'))

        if not payment_id or not price:
            return JsonResponse({'error': 'Invalid input'}, status=400)

        order = Order.objects.filter(id=payment_id).first()
        if not order:
            return JsonResponse({'error': 'Order not found'}, status=404)

        refund_orders = RefundOrder.objects.filter(payment_id=payment_id).all()
        price_all = int(price)
        if refund_orders:
            for refund in refund_orders:
                price_all += int(refund.price)

        if price_all > int(order.price):
            return JsonResponse({'error': 'Refund amount exceeds the payment amount'}, status=400)

        from_account = User.objects.get(id=request.session['id'])
        if from_account.balance < price:
            return JsonResponse({'error': 'Not enough balance'}, status=400, safe=False)

        to_account = User.objects.get(id=order.to_account)

        with transaction.atomic():
            RefundOrder.objects.create(refund_time=datetime.now(), payment_id=payment_id, price=price)

            from_account.balance += price
            from_account.save()

            to_account.balance -= price
            to_account.save()

            order.from_account += price
            order.save()

        return JsonResponse('Success', status=200, safe=False)

    except Exception as e:
        return JsonResponse(str(e), status=500, safe=False)


@api_view(['GET'])
def Balance(request):
    if not request.session.get('id'):
        return JsonResponse({'error': 'No login'}, status=401)
    try:
        user = User.objects.get(id=request.session['id'])
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=404)
    balance = user.balance
    return JsonResponse({'Balance': balance}, status=200)


@api_view(['POST'])
def Deposit(request):
    if request.session:
        data = json.loads(request.body)
        price = data.get('Price')

        if not price:
            return JsonResponse({'Error': 'Price is missing'}, status=400)

        try:
            price = int(price)
        except ValueError:
            return JsonResponse({'Error': 'Price should be an integer'}, status=400)

        if price <= 0:
            return JsonResponse({'Error': 'Price should be greater than zero'}, status=400)

        account = User.objects.get(id=request.session['id'])
        account.balance += price
        account.save()
        return JsonResponse({'Success': True}, status=200)

    return JsonResponse({'Error': 'No login'}, status=400)


@api_view(['POST'])
def Search(request):
    if request.method != 'POST':
        return JsonResponse({'message': 'Invalid request method'}, status=400)
    else:
        if request.session:
            id = request.session['id']
            pages = int(request.POST.get('pages'))
            entries_per_page = int(request.POST.get('EntriesPerPage'))

        else:
            return JsonResponse({'message': 'Please Login'}, status=422)

        orders = Order.objects.filter(from_account=id, to_account=id)

        show_list = []
        for order in orders:
            show = {
                "Type": "Order",
                "PaymentId": order.payment_id,
                "Price": order.price,
                "ToAccount": order.to_account,
                "FromAccount": order.from_account,
                "OrderTime": order.order_time.strftime('%Y-%m-%d %H:%M:%S'),
                "PaymentTime": order.payment_time.strftime('%Y-%m-%d %H:%M:%S')
            }

            # Search RefundOrder table for refunds on this payment_id
            refunds = RefundOrder.objects.filter(payment_id=order.payment_id)
            for refund in refunds:
                refund_show = {
                    "Type": "Refund Order",
                    "PaymentId": order.payment_id,
                    "Price": refund.price,
                    "ToAccount": order.to_account,
                    "FromAccount": order.from_account,
                    "OrderTime": refund.refund_time.strftime('%Y-%m-%d %H:%M:%S'),
                    "PaymentTime": refund.refund_time.strftime('%Y-%m-%d %H:%M:%S')
                }
                show_list.append(refund_show)

            show_list.append(show)

        show_list.sort(key=lambda x: (
            datetime.strptime(x["PaymentTime"], '%Y-%m-%d %H:%M:%S') if x["PaymentTime"] else datetime.min,
            datetime.strptime(x["OrderTime"], '%Y-%m-%d %H:%M:%S')))

        start_idx = entries_per_page * (pages - 1)
        end_idx = entries_per_page * pages
        paginated_show_list = show_list[start_idx:end_idx]

        return JsonResponse(paginated_show_list, status=200, safe=False)
