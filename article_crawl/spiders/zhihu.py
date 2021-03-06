# -*- coding: utf-8 -*-
import re
import time
import json
import scrapy
from PIL import Image
from urllib import parse
from article_crawl.items import CustomItemLoader, ZhihuQuestionItem, ZhihuAnswerItem

class ZhihuSpider(scrapy.Spider):
    name = "zhihu"
    allowed_domains = ["www.zhihu.com"]
    start_urls = ['https://www.zhihu.com/']
    answer_url = 'https://www.zhihu.com/api/v4/questions/{}/answers?include=data%5B*%5D.is_normal%2Cis_sticky%2Ccollapsed_by%2Csuggest_edit%2Ccomment_count%2Ccan_comment%2Ccontent%2Ceditable_content%2Cvoteup_count%2Creshipment_settings%2Ccomment_permission%2Cmark_infos%2Ccreated_time%2Cupdated_time%2Crelationship.is_authorized%2Cis_author%2Cvoting%2Cis_thanked%2Cis_nothelp%2Cupvoted_followees%3Bdata%5B*%5D.author.badge%5B%3F(type%3Dbest_answerer)%5D.topics&offset={}&limit=20&sort_by=default'
    headers = {'Host':'www.zhihu.com', 'Origin':'https://www.zhihu.com','Referer':'https://www.zhihu.com/?next=%2Fsettings%2Fprofile',
               'User-Agent': 'Mozilla/5.0 (Windows NT 5.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/50.0.2661.102 Safari/537.36'}

    def parse(self, response):
        #从知乎首页获取所有问题页面
        all_urls = response.xpath('//a/@href').extract()
        urls_match = filter(lambda x: False if x==None else True, [re.search(r'(/question/(\d+?))/answer',i) for i in all_urls])
        urls = set([i.group(1) for i in urls_match])
        for i in urls:
            url = parse.urljoin(response.url, i)
            question_id = re.search(r'(\d+)', i).group()
            yield scrapy.Request(url=url, headers=self.headers, meta={'question_id':question_id},callback=self.parse_question)

    def parse_question(self, response):

        # zhihuitem = ZhihuItem()
        # topics = response.xpath('//span[@class="Tag-content"]//text()').extract()
        # title = response.xpath('//h1/text()').extract_first()
        # content = response.xpath('//div[@class="QuestionHeader-detail"]//text()').extract_first()
        # answer_num = response.xpath('//h4[@class="List-headerText"]//text()').extract_first()
        # answer_numd = re.search(r'(^\d+)', answer_num).group(1)
        # view_num = response.xpath('//div[@class="NumberBoard-value"]//text()').extract()[-1]
        # url = response.url
        # question_id = response.meta['question_id']
        question_id = response.meta['question_id']

        item_loader = CustomItemLoader(item=ZhihuQuestionItem(), response=response)
        item_loader.add_xpath('topics', '//span[@class="Tag-content"]//text()')
        item_loader.add_xpath('title', '//h1/text()')
        # item_loader.add_xpath('content', '//div[@class="QuestionHeader-detail"]//text()')
        item_loader.add_xpath('answer_num', '//h4[@class="List-headerText"]//text()')
        view_num = response.xpath('//div[@class="NumberBoard-value"]//text()').extract()[-1]
        item_loader.add_value('view_num', view_num)
        item_loader.add_value('url', response.url)
        item_loader.add_value('question_id', question_id)
        item_loader.add_value('crawl_time', time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))

        question_item = item_loader.load_item()
        yield question_item

        yield scrapy.Request(url=self.answer_url.format(question_id, '0'), headers=self.headers, callback=self.parse_answer)

    def parse_answer(self, response):
        answer_json = json.loads(response.text)

        #answer数据
        for data in answer_json['data']:
            answer_item = ZhihuAnswerItem()

            answer_item['answer_id'] = data['id']
            answer_item['question_id'] = data['question']['id']
            answer_item['url'] = 'https://www.zhihu.com/question/{}/answer/{}'.format(data['question']['id'], data['id'])
            answer_item['author_id'] = data['author']['id']
            answer_item['author_name'] = data['author']['name']
            # answer_item['content'] = data['content'] if 'content' in data else data['excerpt']  #content可能不存在
            answer_item['content'] = data['content']
            answer_item['vote_num'] = data['voteup_count']
            answer_item['comment_num'] = data['comment_count']
            answer_item['create_time'] = time.strftime('%Y-%m-%d',time.localtime(data['created_time']))
            answer_item['update_time'] = time.strftime('%Y-%m-%d', time.localtime(data['updated_time']))
            answer_item['crawl_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
            # answer_item['crawl_update_time'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())

            yield answer_item

        #answer分页参数，用于判断answer是否爬取完毕
        is_end = answer_json['paging'].get('is_end')
        next_url = answer_json['paging'].get('next')

        if not is_end:
            yield scrapy.Request(next_url, headers=self.headers, callback=self.parse_answer)

    def start_requests(self):
        return [scrapy.Request(url='https://www.zhihu.com/#signin', headers=self.headers, callback=self.get_loginVal)]

    def get_loginVal(self, response):
        #获取登录前的参数：xsrf值；图片验证码.
        imgCaptcha_url = 'https://www.zhihu.com/captcha.gif?r={}&type=login'.format(str(int(time.time() * 1000)))
        xsrf_match = re.search(r'name="_xsrf" value="(.*?)"', response.text)
        if xsrf_match:
            xsrf = xsrf_match.group(1)
            post_data = {'_xsrf': xsrf, 'phone_num': '你的手机号', 'password': '你的密码','captcha':''}
            yield scrapy.Request(url=imgCaptcha_url, headers=self.headers, meta={'post_data':post_data}, callback=self.captcha_login)

    def captcha_login(self, response):
        post_num_url = 'https://www.zhihu.com/login/phone_num'
        post_data = response.meta.get('post_data', {})
        with open('captcha.jpg', 'wb') as i:
            i.write(response.body)
        try:
            img = Image.open('captcha.jpg')
            img.show()
        except:
            pass
        captcha = input('Please input capthcha:\n>')
        post_data['captcha'] = captcha

        return [scrapy.FormRequest(url=post_num_url, headers=self.headers, formdata=post_data, callback=self.check_login)]

    def check_login(self, response):
        response_text = response.text
        status = json.loads(response_text)
        if status.get('msg', '') == "登录成功":
            for url in self.start_urls:
                yield scrapy.Request(url, headers=self.headers, dont_filter=True)
