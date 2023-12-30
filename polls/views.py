from django.shortcuts import render, redirect, get_object_or_404
from .models import Category, Product, CustomUser, Cart, Order, OrderItem, WebsiteStats
from .forms import RegistrationForm, PaymentForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import LoginForm
from django.db.models import Q, F
from django.http import HttpResponseRedirect
from django.views.decorators.cache import cache_page
import logging
from django.utils.functional import SimpleLazyObject
import hashlib
import hmac
import json
import urllib
import urllib.parse
import urllib.request
import random
import requests
from datetime import datetime
from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect
#from django.utils.http import urlquote
from decimal import Decimal
from .vnpay import *
import datetime

def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            form.save()
            if request.user.is_authenticated:
                logout(request)
            return JsonResponse({'result': "Thanh cong"})
    else:
        form = RegistrationForm()
    return render(request, 'polls/register_index.html', {'form': form})

def forgot_pass_view(request):
    return render(request, 'polls/forgot_pass_index.html')

def homepage_view(request):
    if request.user.is_authenticated and isinstance(request.user._wrapped if hasattr(request.user, '_wrapped') else request.user, CustomUser):
        # User is authenticated, perform actions accordingly
        # Lấy và tăng số lượng lượt truy cập tổng
        increment_total_visits()
        update_user_stats()
        # Lấy sản phẩm nổi bật
        feature_products = Product.objects.all()[:4]
        return render(request, 'polls/homepage_index.html', {'user': request.user, 'feature_products': feature_products})
    else:
        # User is not authenticated, perform actions accordingly
        feature_products = Product.objects.all()[:4]
        return render(request, 'polls/homepage_index2.html', {'feature_products': feature_products})

# Hàm tăng số lượng lượt truy cập tổng
def increment_total_visits():
    latest_stats = WebsiteStats.objects.latest('timestamp')

    # Increment the total_visits
    latest_stats.total_visits += 1
    latest_stats.save()

    return latest_stats.total_visits

def update_user_stats():
    latest_stats = WebsiteStats.objects.latest('timestamp')
    latest_stats.total_registered_users = WebsiteStats.calculate_total_registered_users()
    latest_stats.save()
    return latest_stats.total_registered_users
def login_view(request):
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            # Extract username and password from the form
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            # Use authenticate function to check credentials
            user = authenticate(request, username=username, password=password)

            if user is not None:
                # Authentication successful
                login(request, user)
                return homepage_view(request)
            else:
                # Authentication failed
                messages.error(request, 'Invalid username or password')
        else:
            messages.error(request, 'Invalid form submission')
    else:
        form = LoginForm()

    return render(request, 'polls/login_index.html', {'form': form})
@login_required
def cart_view(request):
    user = request.user
    list_item=[]
    cart = Cart.objects.filter(user=user)
    for c in cart:
        list_item.append(c.product_id)
    
    item = Product.objects.filter(
        id__in=list_item
    )
    return render(request, 'polls/shopping_cart_index.html', {'items': item, 'cart': cart})

def listbooks_view(request):
    products = Product.objects.all()
    return render(request, 'polls/list_book_index.html', {'products': products})

def logout_view(request):
    logout(request)
    feature_products = Product.objects.all()[:4]
    return render(request, 'polls/homepage_index2.html', {'feature_products': feature_products})

def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, in_stock=True)
    related_products = Product.objects.filter(category=product.category)[:4]
    return render(request, 'polls/onlybooks.html', {'product': product, 'related_products': related_products})

def category_list(request, category_slug):
    category = get_object_or_404(Category, slug=category_slug)
    products = Product.objects.filter(category=category)
    return render(request, 'polls/list_book_index.html', {'category': category,'products': products})

def search(request):
    search_product = request.GET.get('search')
    uppercase_product = str(search_product).upper()
    products = ''
    if search_product:
        products = Product.objects.filter(Q(title__icontains=uppercase_product) & Q(description__icontains=uppercase_product))
    else:
    # If not searched, return default posts
        products = ''
    if products:
        count = products.count()
    else:
        count = 0
    return render(request, 'polls/search_product.html', {'products': products, 'search_product': search_product, 'count': count})

@login_required
def add_cart(request, product_id, quantity):
    user = request.user
    cart = Cart.objects.filter(user=user, product_id=product_id)
    if request.POST.get('amount'):
        quantity = request.POST.get('amount')
        quantity = int(quantity)
        
    if cart.exists():
        existed_cart = Cart.objects.get(user=user, product_id=product_id)
        existed_cart.quantity += quantity
        existed_cart.save()
    else:
        new_cart = Cart.objects.create(user=user, product_id=product_id, quantity = 1)
    return homepage_view(request)

@login_required
def update_from_cart(request, product_id, quantity):
    user = request.user
    cart = Cart.objects.get(user=user, product_id=product_id)
    
    quantity = int(quantity)
    cart.quantity = quantity
    cart.save()
    return homepage_view(request)

@login_required
def remove_from_cart(request, cart_id):
    cart = get_object_or_404(Cart, pk=cart_id)
    if request.method == 'POST':
        cart.delete()
    return render(request, 'polls/shopping_cart_index.html')

@login_required
def account_view(request):
    user = request.user
    orders = Order.objects.filter(user=user, paid=True)
    items = OrderItem.objects.filter(order__in=orders)
    total_order = len(orders)
    return render(request, 'polls/account_index.html', {'total_order': total_order, 'orders': orders, 'items': items, 'user': user})

def hmacsha512(key, data):
    byteKey = key.encode('utf-8')
    byteData = data.encode('utf-8')
    return hmac.new(byteKey, byteData, hashlib.sha512).hexdigest()

@login_required
def payment_view(request):
    user = request.user
    list_item=[]
    cart = Cart.objects.filter(user=user).order_by('-product_id')
    for c in cart:
        list_item.append(c.product_id)
    
    item = Product.objects.filter(
        id__in=list_item
    ).order_by('-id')
    total_amount = 0
    for i in range (0, len(cart)):
        total_amount += cart[i].quantity * item[i].price
    return render(request, 'polls/pay_index.html', 
                  {
                      'cart': cart,
                      'items': item,
                      'total_amount': total_amount
                  })

def create_order_item(request, order_id):
    user = request.user
    cart = Cart.objects.filter(user=user).order_by('-product_id')
    list_item = []

    for c in cart:
        list_item.append(c.product_id)
    
    item = Product.objects.filter(
        id__in=list_item
    ).order_by('-id')

    for i in range (0, len(cart)):
        prod = Product.objects.get(id=cart[i].product_id)
        order = Order.objects.get(id=order_id)
        quantity = cart[i].quantity
        price = item[i].price
        new_order_item = OrderItem.objects.create(product=prod, order=order, quantity=quantity, price=price)

def payment(request):
    if request.method == 'POST':
        # Process input data and build url payment
        #form = PaymentForm(request.POST)
        #print(request.POST)
        #if form.is_valid():
            order_type = "Sach/Bao/Tap chi"
            order_id = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            order_desc = "Test thanh toan tu VNPAY"
            bank_code = ''
            language = "vi"
            ipaddr = get_client_ip(request)
            amount = int(request.POST.get('pay_total'))
            name = request.POST.get('pay_username')
            phone_num = request.POST.get('pay_phonenumber')
            address = request.POST.get('pay_address')
            new_order = Order.objects.create(user=request.user, name=name, phone_num=phone_num, address=address, transaction_id=order_id)
            create_order_item(request, new_order.id)
            
            # Build URL Payment
            vnp = vnpay()
            vnp.requestData['vnp_Version'] = '2.1.0'
            vnp.requestData['vnp_Command'] = 'pay'
            vnp.requestData['vnp_TmnCode'] = settings.VNPAY_TMN_CODE
            vnp.requestData['vnp_Amount'] = amount * 100
            vnp.requestData['vnp_CurrCode'] = 'VND'
            vnp.requestData['vnp_TxnRef'] = order_id
            vnp.requestData['vnp_OrderInfo'] = order_desc
            vnp.requestData['vnp_OrderType'] = order_type
            # Check language, default: vn
            if language and language != '':
                vnp.requestData['vnp_Locale'] = language
            else:
                vnp.requestData['vnp_Locale'] = 'vn'
                # Check bank_code, if bank_code is empty, customer will be selected bank on VNPAY
            if bank_code and bank_code != "":
                vnp.requestData['vnp_BankCode'] = bank_code
            vnp.requestData['vnp_CreateDate'] = datetime.datetime.now().strftime('%Y%m%d%H%M%S')  # 20150410063022
            vnp.requestData['vnp_IpAddr'] = ipaddr
            vnp.requestData['vnp_ReturnUrl'] = settings.VNPAY_RETURN_URL
            vnpay_payment_url = vnp.get_payment_url(settings.VNPAY_PAYMENT_URL, settings.VNPAY_HASH_SECRET_KEY)
            print(vnpay_payment_url)
            return redirect(vnpay_payment_url)
        #else:
        #    print("Form input not validate")
    else:
        return render(request, "polls/homepage_index.html", {"title": "Thanh toán"})
    

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def payment_return(request):
    inputData = request.GET
    if inputData:
        vnp = vnpay()
        vnp.responseData = inputData.dict()
        order_id = inputData['vnp_TxnRef']
        amount = int(inputData['vnp_Amount']) / 100
        order_desc = inputData['vnp_OrderInfo']
        vnp_TransactionNo = inputData['vnp_TransactionNo']
        vnp_ResponseCode = inputData['vnp_ResponseCode']
        vnp_TmnCode = inputData['vnp_TmnCode']
        vnp_PayDate = inputData['vnp_PayDate']
        vnp_BankCode = inputData['vnp_BankCode']
        vnp_CardType = inputData['vnp_CardType']
        if vnp.validate_response(settings.VNPAY_HASH_SECRET_KEY):
            if vnp_ResponseCode == "00":
                payment_success(order_id)
                return render(request, "polls/payment_return.html", {"title": "Kết quả thanh toán",
                                                               "result": "Thanh toán thành công. Cảm ơn các bạn đã tin tưởng Nhà của Cú",
                                                                "order_id": order_id,
                                                               "amount": amount,
                                                               "order_desc": order_desc,
                                                               "vnp_TransactionNo": vnp_TransactionNo,
                                                               "vnp_ResponseCode": vnp_ResponseCode})
            else:
                payment_fail(order_id)
                return render(request, "polls/payment_return.html", {"title": "Kết quả thanh toán",
                                                               "result": "Thanh toán thất bại. Vui lòng thử lại sau.", "order_id": order_id,
                                                               "amount": amount,
                                                               "order_desc": order_desc,
                                                               "vnp_TransactionNo": vnp_TransactionNo,
                                                               "vnp_ResponseCode": vnp_ResponseCode})
        else:
            payment_fail(order_id)
            return render(request, "polls/payment_return.html",
                          {"title": "Kết quả thanh toán", "result": "Thanh toán thất bại. Vui lòng thử lại sau.", 
                           "order_id": order_id, "amount": amount,
                           "order_desc": order_desc, "vnp_TransactionNo": vnp_TransactionNo,
                           "vnp_ResponseCode": vnp_ResponseCode, "msg": "Sai checksum"})
    else:
        payment_fail(order_id)
        return render(request, "polls/payment_return.html", {"title": "Kết quả thanh toán", "result": ""})

def payment_success(order_id):
    order = Order.objects.get(transaction_id=order_id)
    order_items = OrderItem.objects.filter(order=order)

    total_price = sum(item.price * item.quantity for item in order_items)
    total_quantity = sum(item.quantity for item in order_items)
    
    WebsiteStats.objects.update(
        total_sales=F('total_sales') + total_price,
        total_sold_products=F('total_sold_products') + total_quantity
    )
    order.paid = True
    order.save()
    user = order.user
    cart = Cart.objects.filter(user=user)
    for c in cart:
        c.delete()

def payment_fail(order_id):
    order = Order.objects.get(transaction_id=order_id)
    order_items = OrderItem.objects.filter(order=order)
    for item in order_items:
        item.delete()