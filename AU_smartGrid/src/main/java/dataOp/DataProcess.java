package main.java.dataOp;

import java.util.ArrayList;
import java.util.Random;

import main.java.model.ConstNum;
import main.java.model.Device;
import main.java.model.Station;

import java.io.File;
import java.io.FileInputStream;
import java.time.ZonedDateTime;
import java.time.ZoneId;

import org.apache.poi.ss.usermodel.*;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;

public class DataProcess {
    public static Station getStation(Random rad) {
        Station station = new Station();
        ArrayList<Double> prices = new ArrayList<>();

        // ==========================================
        // 修改部分
        // 先获取Asia/Shanghai时区的当前小时数与分钟数
        // 因为每个timeSlots代表15分钟 所以如果是13:45开始 下两个应该是14:00以及14:15
        // 应该 一个为13点的电价 两个为14点的电价 因此同时需要小时和分钟
        ZonedDateTime shanghaiTime = ZonedDateTime.now(ZoneId.of("Asia/Shanghai"));
        int currentHour = shanghaiTime.getHour();
        int currentMinute = shanghaiTime.getMinute();

        // 再读取price.xlsx（目前是放在模型同目录）
        try (FileInputStream fis = new FileInputStream(new File("price.xlsx"));
             Workbook workbook = new XSSFWorkbook(fis)) {
            Sheet sheet = workbook.getSheetAt(0);

            // timeSlots长度
            for (int i = 0; i < ConstNum.timeSlots; i++) {

                // minutes偏移量
                // 例如 i=0 是偏移0分钟，i=1 是偏移15分钟，i=2 是偏移30分钟
                int offsetMinutes = i * 15;

                // 先算出总分钟 然后加上偏移量
                // 这样可以处理分钟进位导致小时改变的情况（如 13:45 + 15min = 14:00）
                // 再算出 目标小时
                int totalMinutes = (currentHour * 60 + currentMinute) + offsetMinutes;
                int targetHour = (totalMinutes / 60) % 24; // 换算成 0-23 小时

                // 根据换算后的 targetHour 去 Excel 找对应的行
                // 然后填入prices中
                Row row = sheet.getRow(targetHour + 1);
                if (row != null) {
                    // 单位换算
                    double priceValue = row.getCell(2).getNumericCellValue() / 1000;
                    prices.add(priceValue);
                } else {
                    prices.add(0.0);
                }
            }
        } catch (Exception e) {
            //若读取excel失败，就用之前的方法
            System.err.println("读取 price.xlsx 失败，回退至随机电价。");
            for(int i = 0; i < ConstNum.timeSlots; i++) {
                prices.add(rad.nextDouble());
            }
        }
        // ==========================================
        station.setMaxCharge(1);
        station.setMaxDischarge(1);
        station.setPrice(prices);
        return station;
    }


    public static ArrayList<Device> getDevices(Random rad){
        ArrayList<Device> devices = new ArrayList<>();

        for(int i=0;i<ConstNum.nDevices;i++) {
            Device device = new Device();
            device.setId(i);

            double overallCapacity = rad.nextDouble(0.5,1);
            device.setOverallCapacity(overallCapacity);

            ArrayList<Double> currentStorage = new ArrayList<>();
            ArrayList<Double> demands = new ArrayList<>();
            ArrayList<Double> produce = new ArrayList<>();
            ArrayList<Double> chargeSpeed = new ArrayList<>();
            ArrayList<Double> disChargeSpeed = new ArrayList<>();
            ArrayList<Double> chargeCost = new ArrayList<>();
            ArrayList<Double> disChargeCost = new ArrayList<>();
            for(int j=0;j<ConstNum.timeSlots;j++) {
                currentStorage.add(rad.nextDouble(0.5));
                demands.add(rad.nextDouble(0.5));
                produce.add(rad.nextDouble(0.5));
            }
            device.setCurrentStorage(currentStorage);
            device.setDemands(demands);
            device.setProduce(produce);

            for(int j=0;j<ConstNum.nChargeLevels;j++) {
                double speed = rad.nextDouble();
                chargeSpeed.add(speed);
                chargeCost.add(speed/10);
            }
            for(int j=0;j<ConstNum.nDischargeLevels;j++) {
                double speed = rad.nextDouble();
                disChargeSpeed.add(speed);
                disChargeCost.add(speed/10);
            }

            device.setAgreementPrice(rad.nextDouble()/2);

            device.setChargeSpeed(chargeSpeed);
            device.setChargeCost(chargeCost);
            device.setDischargeSpeed(disChargeSpeed);
            device.setDischargeCost(disChargeCost);

            devices.add(new Device(device));
        }

        return devices;
    }
	
}