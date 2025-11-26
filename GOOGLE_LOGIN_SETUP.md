# 如何启用Firebase Google登录

## 📋 当前状态

✅ **代码已实现** - Login.html中已经包含Google登录功能  
⚠️ **需要配置** - 需要在Firebase Console中启用Google登录

---

## 🔧 配置步骤

### 第一步：访问Firebase Console

1. 打开 [Firebase Console](https://console.firebase.google.com/)
2. 选择您的项目：**touringbank**

### 第二步：启用Google登录

1. 在左侧菜单中，点击 **"Authentication"** (身份验证)
2. 点击 **"Sign-in method"** (登录方法) 标签
3. 在提供商列表中找到 **"Google"**
4. 点击 **"Google"** 行右侧的编辑图标（铅笔图标）

### 第三步：配置Google登录

在弹出的对话框中：

1. **启用开关** - 将开关切换到"启用"状态
2. **项目支持电子邮件** - 输入您的邮箱（例如：your-email@gmail.com）
   - 这个邮箱会在OAuth同意屏幕上显示
3. 点击 **"保存"** 按钮

### 第四步：（可选）配置授权域名

如果您要在自定义域名上使用：

1. 在 **"Settings"** (设置) 标签中
2. 找到 **"Authorized domains"** (授权域名)
3. 默认已包含：
   - `localhost`
   - `yourdomain.firebaseapp.com`
4. 如果需要添加自定义域名，点击 **"Add domain"**

---

## ✅ 验证配置

配置完成后，在 **Sign-in method** 页面应该看到：

```
Google                    ✅ 已启用
```

---

## 🧪 测试Google登录

### 方法1：本地测试

1. 打开 `Login.html` 文件
2. 点击 **"Google"** 按钮
3. 会弹出Google账户选择窗口
4. 选择您的Google账户
5. 授权后自动登录

### 方法2：查看代码

Google登录的代码已经在 `Login.html` 中实现：

```javascript
// Google登录按钮点击事件
const googleLoginBtn = document.getElementById('googleLoginBtn');
googleLoginBtn.addEventListener('click', async function() {
    const provider = new firebase.auth.GoogleAuthProvider();
    provider.setCustomParameters({
        prompt: 'select_account'
    });
    
    try {
        const result = await auth.signInWithPopup(provider);
        const user = result.user;
        
        console.log('Google登录成功:', user);
        alert('登录成功！');
        window.location.href = 'index.html';
        
    } catch (error) {
        console.error('Google登录失败:', error);
        alert('Google登录失败');
    }
});
```

---

## 🎯 工作原理

1. **用户点击Google按钮**
2. **Firebase弹出Google登录窗口**
3. **用户选择Google账户**
4. **Google返回用户信息**
5. **Firebase自动创建/登录用户**
6. **跳转到首页，显示登录状态**

---

## 🔍 常见问题

### Q1: 点击Google登录没反应？

**解决方案：**
1. 检查浏览器控制台（F12）是否有错误
2. 确认已在Firebase Console启用Google登录
3. 确认 `firebase-config.js` 配置正确

### Q2: 显示"此应用未经验证"？

**解决方案：**
这是正常的，因为应用还在开发阶段。点击 **"高级"** → **"转到 touringbank（不安全）"** 即可继续。

要移除此警告，需要：
1. 在Google Cloud Console配置OAuth同意屏幕
2. 提交应用审核（仅生产环境需要）

### Q3: 弹出窗口被浏览器拦截？

**解决方案：**
1. 允许浏览器弹出窗口
2. 或使用 `signInWithRedirect` 代替 `signInWithPopup`

---

## 📊 登录后的用户信息

Google登录成功后，可以获取：

- ✅ **邮箱** - `user.email`
- ✅ **显示名** - `user.displayName`
- ✅ **头像** - `user.photoURL`
- ✅ **用户ID** - `user.uid`

这些信息会自动显示在首页右上角！

---

## 🎨 UI展示

### 登录页面
```
┌─────────────────────────────┐
│   [邮箱输入框]              │
│   [密码输入框]              │
│   [登录按钮]                │
│                             │
│   或使用以下方式登录         │
│                             │
│   [🔴 Google]  [⚫ GitHub]  │
└─────────────────────────────┘
```

### 登录后首页
```
导航栏右上角：
[👤 your-name ▼]
    │
    ├─ 个人中心
    ├─ 我的清单
    └─ 退出登录
```

---

## ✨ 额外功能

### 自定义Google登录参数

如果需要自定义，可以修改 `Login.html` 中的代码：

```javascript
const provider = new firebase.auth.GoogleAuthProvider();

// 强制选择账户
provider.setCustomParameters({
    prompt: 'select_account'
});

// 请求额外权限（可选）
provider.addScope('https://www.googleapis.com/auth/userinfo.email');
provider.addScope('https://www.googleapis.com/auth/userinfo.profile');
```

---

## 🚀 下一步

配置完成后，您的用户可以：

1. ✅ 使用邮箱密码注册/登录
2. ✅ 使用Google账户一键登录
3. ✅ 使用GitHub账户登录（需要单独配置）
4. ✅ 在首页看到登录状态
5. ✅ 随时退出登录

---

**需要帮助？** 查看 [Firebase Authentication 文档](https://firebase.google.com/docs/auth/web/google-signin)
